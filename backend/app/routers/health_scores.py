from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.client import Client
from app.models.health_history import ClientHealthHistory, ClientHealthScoreEvent
from app.utils.deps import get_current_user
from app.utils.scoped_query import scoped

router = APIRouter()


def _event_severity(delta: int, score: int) -> str:
    if score < 50 or delta <= -20:
        return "critical"
    if score < 75 or delta <= -10:
        return "warning"
    return "info"


def _component_manifest(result: dict) -> dict:
    components = result.get("components", {})
    max_points = {"gst": 25, "itc": 25, "notices": 25, "anomaly": 15, "tds": 10}
    deductions = {
        key: round(max_points[key] - float(components.get(key, 0)), 2)
        for key in max_points
    }
    drivers = sorted(
        [{"metric": key, "deduction": value} for key, value in deductions.items() if value > 0],
        key=lambda item: item["deduction"],
        reverse=True,
    )
    return {"components": components, "deductions": deductions, "top_drivers": drivers[:3]}


def _explain(client: Client, previous_score: int | None, current_score: int, manifest: dict) -> str:
    delta = current_score - previous_score if previous_score is not None else 0
    direction = "improved" if delta > 0 else "dropped" if delta < 0 else "remained stable"
    driver_text = ", ".join(f"{item['metric']} deduction {item['deduction']}" for item in manifest["top_drivers"]) or "no material deductions"
    return f"{client.name} health score {direction} to {current_score}/100. Primary drivers: {driver_text}."


def _trend(db: Session, org_id, client_id: str, current_score: int) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=7)
    past = (
        scoped(db, ClientHealthHistory, org_id)
        .filter(ClientHealthHistory.client_id == client_id, ClientHealthHistory.computed_at <= since)
        .order_by(ClientHealthHistory.computed_at.desc())
        .first()
    )
    recent = (
        scoped(db, ClientHealthHistory, org_id)
        .filter(ClientHealthHistory.client_id == client_id)
        .order_by(ClientHealthHistory.computed_at.desc())
        .limit(30)
        .all()
    )
    seven_day_delta = current_score - past.score if past else None
    scores = [row.score for row in recent]
    moving_average = round(sum(scores) / len(scores), 2) if scores else current_score
    return {
        "seven_day_delta": seven_day_delta,
        "moving_average_30": moving_average,
        "trajectory": "deteriorating" if seven_day_delta is not None and seven_day_delta <= -10 else "improving" if seven_day_delta is not None and seven_day_delta >= 10 else "stable",
    }


@router.get("")
def get_all_health_scores(request: Request, db: Session = Depends(get_db),
                           _=Depends(get_current_user)):
    clients = (scoped(db, Client, request.state.org_id)
               .order_by(Client.health_score.asc()).all())
    return [{
        "id": str(c.id), "name": c.name,
        "health_score": c.health_score,
        "tier": "green" if c.health_score >= 75 else "amber" if c.health_score >= 50 else "red",
    } for c in clients]


@router.post("/recompute/{client_id}")
def recompute(client_id: str, request: Request,
              db: Session = Depends(get_db), _=Depends(get_current_user)):
    from app.engines.health_score_engine import compute_health_score
    from app.models.client import Client as ClientModel

    client = (scoped(db, ClientModel, request.state.org_id)
              .filter(ClientModel.id == client_id, ClientModel.status == "active").first())
    if not client:
        raise HTTPException(404, "Client not found")

    previous = (
        scoped(db, ClientHealthHistory, request.state.org_id)
        .filter(ClientHealthHistory.client_id == client_id)
        .order_by(ClientHealthHistory.computed_at.desc())
        .first()
    )
    result = compute_health_score(client_id, db)
    previous_score = previous.score if previous else None
    delta = result["score"] - previous_score if previous_score is not None else 0
    manifest = _component_manifest(result)
    trend = _trend(db, request.state.org_id, client_id, result["score"])
    manifest["trend"] = trend
    client.health_score = result["score"]
    history = ClientHealthHistory(
        org_id=request.state.org_id, client_id=client_id,
        score=result["score"], tier=result["tier"],
        components=result["components"],
    )
    db.add(history)
    is_baseline_snapshot = bool((previous.components or {}).get("baseline")) if previous else False
    if previous_score is None or is_baseline_snapshot or abs(delta) >= 5 or trend["trajectory"] == "deteriorating":
        db.add(ClientHealthScoreEvent(
            org_id=request.state.org_id,
            client_id=client_id,
            event_type="HEALTH_SCORE_RECOMPUTED",
            severity=_event_severity(delta, result["score"]),
            previous_score=previous_score,
            current_score=result["score"],
            delta=delta,
            reason_manifest=manifest,
            explanation=_explain(client, previous_score, result["score"], manifest),
        ))
    db.commit()
    return {**result, "delta": delta, "trend": trend, "explanation": _explain(client, previous_score, result["score"], manifest)}


@router.get("/{client_id}/analysis")
def health_analysis(client_id: str, request: Request,
                    db: Session = Depends(get_db), _=Depends(get_current_user)):
    client = scoped(db, Client, request.state.org_id).filter(Client.id == client_id, Client.status == "active").first()
    if not client:
        raise HTTPException(404, "Client not found")
    history = (
        scoped(db, ClientHealthHistory, request.state.org_id)
        .filter(ClientHealthHistory.client_id == client_id)
        .order_by(ClientHealthHistory.computed_at.desc())
        .limit(90)
        .all()
    )
    events = (
        scoped(db, ClientHealthScoreEvent, request.state.org_id)
        .filter(ClientHealthScoreEvent.client_id == client_id)
        .order_by(ClientHealthScoreEvent.created_at.desc())
        .limit(20)
        .all()
    )
    latest = history[0] if history else None
    trend = _trend(db, request.state.org_id, client_id, latest.score if latest else client.health_score)
    return {
        "client_id": client_id,
        "current_score": latest.score if latest else client.health_score,
        "current_tier": latest.tier if latest else ("green" if client.health_score >= 75 else "amber" if client.health_score >= 50 else "red"),
        "trend": trend,
        "history": [
            {"score": row.score, "tier": row.tier, "components": row.components, "computed_at": row.computed_at}
            for row in history
        ],
        "events": [
            {
                "id": str(row.id),
                "event_type": row.event_type,
                "severity": row.severity,
                "previous_score": row.previous_score,
                "current_score": row.current_score,
                "delta": row.delta,
                "reason_manifest": row.reason_manifest,
                "explanation": row.explanation,
                "created_at": row.created_at,
            }
            for row in events
        ],
    }
