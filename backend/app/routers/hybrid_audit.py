"""Hybrid Audit Engine (HAE-4) APIs: train, score, prioritize, sample, evaluate."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.anomaly_flag import AnomalyFlag
from app.models.audit_ml import AuditBanditEvent, AuditEngineRun, AuditModelArtifact
from app.models.client import Client
from app.models.transaction import Transaction
from app.plugins.layer2_risk_fusion import plugin_for_org
from app.utils.deps import get_current_user, require_role
from app.utils.scoped_query import scoped

router = APIRouter()


class TrainRequest(BaseModel):
    client_id: Optional[str] = None
    async_run: bool = True


class SampleRequest(BaseModel):
    client_id: str
    materiality: float | None = Field(default=None, gt=0)
    review_budget: int = Field(default=25, ge=1, le=500)


class ScoreRequest(BaseModel):
    client_id: str
    async_run: bool = True
    materiality_override: float | None = Field(default=None, gt=0)


class AssertionsRequest(BaseModel):
    client_id: str
    materiality_override: float | None = Field(default=None, gt=0)
    period_end: str | None = None
    cutoff_window_days: int = Field(default=7, ge=1, le=31)


class PrioritizeRequest(BaseModel):
    client_id: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=500)
    firm_capacity: float = Field(default=1.0, ge=0.0, le=1.0)


class BanditFeedbackRequest(BaseModel):
    candidate_id: Optional[str] = None
    arm: int = Field(default=1, ge=0, le=2)
    review_status: str = Field(default="confirmed", min_length=1, max_length=30)
    context: list[float] = Field(default_factory=list)


class ExplainBatchRequest(BaseModel):
    transactions: list[dict[str, Any]] = Field(default_factory=list, min_length=1, max_length=200)


@router.get("/status")
def hae_status(request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    from app.engines import model_registry

    org_id = request.state.org_id
    artifacts = model_registry.list_artifacts(org_id)
    db_artifacts = scoped(db, AuditModelArtifact, org_id).order_by(AuditModelArtifact.created_at.desc()).limit(20).all()
    runs = scoped(db, AuditEngineRun, org_id).order_by(AuditEngineRun.created_at.desc()).limit(10).all()
    scored = (
        scoped(db, Transaction, org_id)
        .filter(Transaction.audit_risk_score.isnot(None))
        .count()
    )
    return {
        "engine": "HAE-5",
        "plugin": plugin_for_org(org_id).status(),
        "mode": "human_auditor_precision",
        "layers": [
            "assertions", "rules", "isolation_forest_lof", "xgboost_lightgbm",
            "temporal_transformer", "graph_sage", "linucb_bandit", "meta_fusion",
        ],
        "assertions": [
            "cutoff", "completeness", "existence", "classification", "related_party",
            "journal_entry", "three_way_match", "aging", "accuracy",
        ],
        "scored_transactions": scored,
        "local_artifacts": artifacts,
        "registry": [
            {
                "id": str(a.id),
                "name": a.name,
                "version": a.version,
                "backend": a.backend,
                "metrics": a.metrics,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in db_artifacts
        ],
        "recent_runs": [
            {
                "id": str(r.id),
                "run_type": r.run_type,
                "status": r.status,
                "summary": r.summary,
                "client_id": str(r.client_id) if r.client_id else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ],
    }


@router.post("/explain")
def explain_transactions(
    payload: ExplainBatchRequest,
    request: Request,
    _=Depends(get_current_user),
):
    plugin = plugin_for_org(request.state.org_id)
    return plugin.analyze_batch(payload.transactions)


@router.post("/train")
def train_models(
    payload: TrainRequest,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_role(["partner", "manager"])),
):
    from app.tasks.hybrid_audit_tasks import train_hybrid_audit_models

    org_id = request.state.org_id
    if payload.client_id:
        client = scoped(db, Client, org_id).filter(Client.id == payload.client_id).first()
        if not client:
            raise HTTPException(404, "Client not found")
    if payload.async_run:
        task = train_hybrid_audit_models.delay(org_id, payload.client_id)
        return {"queued": True, "task_id": task.id, "org_id": org_id}
    result = train_hybrid_audit_models.run(org_id, payload.client_id)
    return {"queued": False, "result": result}


@router.post("/score")
def score_client(
    payload: ScoreRequest,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    from app.tasks.hybrid_audit_tasks import run_hybrid_audit_scoring

    org_id = request.state.org_id
    client = scoped(db, Client, org_id).filter(Client.id == payload.client_id).first()
    if not client:
        raise HTTPException(404, "Client not found")
    if payload.async_run:
        task = run_hybrid_audit_scoring.delay(
            payload.client_id, org_id=org_id, materiality_override=payload.materiality_override
        )
        return {"queued": True, "task_id": task.id, "client_id": payload.client_id}
    result = run_hybrid_audit_scoring.run(
        payload.client_id, org_id=org_id, materiality_override=payload.materiality_override
    )
    return {"queued": False, "result": result}


@router.post("/evaluate")
def evaluate_models(
    payload: TrainRequest,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_role(["partner", "manager"])),
):
    from app.tasks.hybrid_audit_tasks import evaluate_hybrid_audit_models

    org_id = request.state.org_id
    if payload.async_run:
        task = evaluate_hybrid_audit_models.delay(org_id, payload.client_id)
        return {"queued": True, "task_id": task.id}
    return {"queued": False, "result": evaluate_hybrid_audit_models.run(org_id, payload.client_id)}


@router.get("/risks/{client_id}")
def client_risks(
    client_id: str,
    request: Request,
    db: Session = Depends(get_db),
    min_score: float = 0.0,
    limit: int = 100,
    _=Depends(get_current_user),
):
    org_id = request.state.org_id
    client = scoped(db, Client, org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(404, "Client not found")
    if limit < 1 or limit > 2000:
        raise HTTPException(422, "limit must be between 1 and 2000")
    q = (
        scoped(db, Transaction, org_id)
        .filter(Transaction.client_id == client_id, Transaction.audit_risk_score.isnot(None))
    )
    if min_score > 0:
        q = q.filter(Transaction.audit_risk_score >= min_score)
    rows = q.order_by(Transaction.audit_risk_score.desc()).limit(limit).all()
    return [_txn_risk_out(t) for t in rows]


@router.post("/prioritize")
def prioritize_queue(
    payload: PrioritizeRequest,
    request: Request,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    from app.engines.audit_bandit import prioritize_candidates

    org_id = request.state.org_id
    q = scoped(db, AnomalyFlag, org_id).filter(AnomalyFlag.reviewed.is_(False))
    if payload.client_id:
        q = q.filter(AnomalyFlag.client_id == payload.client_id)
    flags = q.order_by(AnomalyFlag.risk_score.desc()).limit(500).all()
    now = datetime.now(timezone.utc)
    candidates = []
    for flag in flags:
        age_hours = 0.0
        if flag.created_at:
            age_hours = max(0.0, (now - flag.created_at).total_seconds() / 3600.0)
        amount = 0.0
        if flag.transaction and flag.transaction.amount is not None:
            amount = float(flag.transaction.amount)
        elif isinstance(flag.details, dict):
            amount = float(flag.details.get("amount") or 0)
        risk = float(flag.risk_score or 0)
        candidates.append({
            "id": str(flag.id),
            "transaction_id": str(flag.transaction_id) if flag.transaction_id else None,
            "client_id": str(flag.client_id),
            "flag_type": flag.flag_type,
            "source_type": "anomaly",
            "risk_prob": risk if risk <= 1 else risk / 100.0,
            "impact_amount": amount,
            "age_hours": age_hours,
            "details": flag.details,
            "drivers": (flag.details or {}).get("drivers") if isinstance(flag.details, dict) else None,
        })
    ranked = prioritize_candidates(
        candidates, org_id=org_id, firm_capacity=payload.firm_capacity
    )[: payload.limit]
    return {"count": len(ranked), "items": ranked}


@router.post("/assertions")
def run_assertions(
    payload: AssertionsRequest,
    request: Request,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Run human-auditor assertion procedures over a client transaction log."""
    from datetime import date as date_cls
    from app.engines.audit_assertions_engine import run_assertion_procedures

    org_id = request.state.org_id
    client = scoped(db, Client, org_id).filter(Client.id == payload.client_id).first()
    if not client:
        raise HTTPException(404, "Client not found")
    txns = scoped(db, Transaction, org_id).filter(Transaction.client_id == payload.client_id).all()
    period_end = None
    if payload.period_end:
        try:
            period_end = date_cls.fromisoformat(payload.period_end)
        except ValueError as exc:
            raise HTTPException(422, "period_end must be YYYY-MM-DD") from exc
    result = run_assertion_procedures(
        txns,
        period_end=period_end,
        materiality_override=payload.materiality_override,
        cutoff_window_days=payload.cutoff_window_days,
    )
    db.add(AuditEngineRun(
        org_id=org_id,
        client_id=payload.client_id,
        run_type="assertions",
        status="completed",
        summary={
            "materiality": result.get("materiality"),
            "period_end": result.get("period_end"),
            "population": result.get("population"),
            "findings": len(result.get("findings") or []),
            "coverage": result.get("coverage"),
        },
    ))
    db.commit()
    return result


@router.post("/sample-plan")
def sample_plan(
    payload: SampleRequest,
    request: Request,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    from app.engines.audit_bandit import adaptive_sample_plan
    from app.engines.audit_assertions_engine import compute_materiality

    org_id = request.state.org_id
    client = scoped(db, Client, org_id).filter(Client.id == payload.client_id).first()
    if not client:
        raise HTTPException(404, "Client not found")
    txns = (
        scoped(db, Transaction, org_id)
        .filter(Transaction.client_id == payload.client_id)
        .all()
    )
    amounts = [float(t.amount or 0) for t in txns]
    mat = compute_materiality(amounts, override=payload.materiality)
    scored = []
    for t in txns:
        assertions = t.audit_assertions if isinstance(getattr(t, "audit_assertions", None), dict) else {}
        scored.append({
            "id": str(t.id),
            "transaction_id": str(t.id),
            "amount": float(t.amount or 0),
            "audit_risk_prob": float(t.audit_risk_prob or t.anomaly_score or 0),
            "drivers": t.audit_risk_drivers,
            "failed_assertions": assertions.get("failed_assertions"),
            "evidence": assertions.get("evidence"),
            "source_type": "anomaly",
        })
    plan = adaptive_sample_plan(
        scored,
        materiality=mat["planning_materiality"],
        performance_materiality=mat["performance_materiality"],
        clearly_trivial=mat["clearly_trivial"],
        review_budget=payload.review_budget,
        org_id=org_id,
    )
    db.add(AuditEngineRun(
        org_id=org_id,
        client_id=payload.client_id,
        run_type="sample",
        status="completed",
        summary={
            "selected_count": plan["selected_count"],
            "coverage_amount": plan["coverage_amount"],
            "population_coverage_pct": plan.get("population_coverage_pct"),
            "materiality": plan["materiality"],
            "performance_materiality": plan.get("performance_materiality"),
            "residual_high_risk_count": plan.get("residual_high_risk_count"),
        },
    ))
    db.commit()
    return plan


@router.post("/bandit/feedback")
def bandit_feedback(
    payload: BanditFeedbackRequest,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    from app.engines.audit_bandit import record_bandit_feedback, CONTEXT_DIM

    org_id = request.state.org_id
    context = payload.context
    if len(context) != CONTEXT_DIM:
        # pad / trim
        context = (list(context) + [0.0] * CONTEXT_DIM)[:CONTEXT_DIM]
    result = record_bandit_feedback(org_id, context, payload.arm, payload.review_status)
    db.add(AuditBanditEvent(
        org_id=org_id,
        candidate_id=payload.candidate_id,
        arm=payload.arm,
        reward=result["reward"],
        review_status=payload.review_status,
        context={"vector": context, "user_id": str(user.id)},
    ))
    db.commit()
    return result


def _txn_risk_out(t: Transaction) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "client_id": str(t.client_id),
        "invoice_no": t.invoice_no,
        "vendor_name": t.vendor_name,
        "vendor_gstin": t.vendor_gstin,
        "amount": float(t.amount or 0) if t.amount is not None else None,
        "date": t.date.isoformat() if t.date else None,
        "anomaly_score": float(t.anomaly_score or 0),
        "audit_risk_score": float(t.audit_risk_score or 0) if t.audit_risk_score is not None else None,
        "audit_risk_prob": float(t.audit_risk_prob or 0) if t.audit_risk_prob is not None else None,
        "audit_confidence": float(t.audit_confidence or 0) if getattr(t, "audit_confidence", None) is not None else None,
        "drivers": t.audit_risk_drivers,
        "layers": t.hae_layer_scores,
        "assertions": getattr(t, "audit_assertions", None),
        "fraud_flag": t.fraud_flag,
        "match_status": t.match_status,
    }
