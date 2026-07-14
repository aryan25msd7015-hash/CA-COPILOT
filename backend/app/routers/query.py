from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.saved_query import SavedQuery
from app.utils.deps import get_current_user
from app.utils.scoped_query import scoped
from app.utils.activity import log_activity
from app.utils.events import publish_event

router = APIRouter()


class AskRequest(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def valid_question(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3 or len(normalized) > 1000:
            raise ValueError("Question must be between 3 and 1000 characters")
        return normalized


class SaveRequest(BaseModel):
    name: str
    nl_query: str

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 1 or len(normalized) > 120:
            raise ValueError("Name must be between 1 and 120 characters")
        return normalized


class SavedQueryUpdateRequest(BaseModel):
    name: str | None = None
    nl_query: str | None = None

    @field_validator("name")
    @classmethod
    def valid_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if len(normalized) < 1 or len(normalized) > 120:
            raise ValueError("Name must be between 1 and 120 characters")
        return normalized

    @field_validator("nl_query")
    @classmethod
    def valid_optional_query(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if len(normalized) < 3 or len(normalized) > 1000:
            raise ValueError("Saved query must be between 3 and 1000 characters")
        return normalized


def _saved_out(row: SavedQuery) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "nl_query": row.nl_query,
        "run_count": row.run_count,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }

    @field_validator("nl_query")
    @classmethod
    def valid_nl_query(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3 or len(normalized) > 1000:
            raise ValueError("Saved query must be between 3 and 1000 characters")
        return normalized

@router.post("/ask")
def ask(payload: AskRequest, request: Request, db: Session = Depends(get_db),
        user=Depends(get_current_user)):
    from app.tasks.llm_tasks import run_nl_query

    task = run_nl_query.delay(payload.question, request.state.org_id)
    log_activity(db, request.state.org_id, user.id, "query_run", None, 600, {"question": payload.question})
    db.commit()
    return {"task_id": task.id}


@router.post("/ask-now")
def ask_now(payload: AskRequest, request: Request, db: Session = Depends(get_db),
            user=Depends(get_current_user)):
    from app.engines.grounded_assistant import grounded_query

    result = grounded_query(payload.question, request.state.org_id, db)
    log_activity(db, request.state.org_id, user.id, "query_run", None, 600, {"question": payload.question, "mode": "ask_now"})
    publish_event(
        db,
        org_id=request.state.org_id,
        actor_id=user.id,
        event_type="assistant.query.answered",
        aggregate_type="assistant_query",
        aggregate_id=f"ask-now:{user.id}",
        source_module="query",
        payload={
            "question": payload.question,
            "provider": result["provider"],
            "confidence": result["confidence"],
            "row_count": result["row_count"],
            "source_count": result["grounding"]["source_count"],
        },
    )
    db.commit()
    return result


@router.get("/starters")
def starters(format: str = "cards", _=Depends(get_current_user)):
    from app.engines.nl_query_engine import STARTER_PROMPTS, STARTER_QUERIES

    if format == "legacy":
        return STARTER_QUERIES
    if format != "cards":
        raise HTTPException(422, "Invalid starter format")
    return STARTER_PROMPTS


@router.get("/saved")
def saved(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user),
          q: str | None = None, skip: int = 0, limit: int = 200):
    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > 1000:
        raise HTTPException(422, "limit must be between 1 and 1000")
    query = scoped(db, SavedQuery, request.state.org_id).filter(SavedQuery.user_id == user.id)
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(or_(SavedQuery.name.ilike(term), SavedQuery.nl_query.ilike(term)))
    rows = query.order_by(SavedQuery.updated_at.desc()).offset(skip).limit(limit).all()
    return [_saved_out(row) for row in rows]


@router.post("/saved", status_code=201)
def save(payload: SaveRequest, request: Request, db: Session = Depends(get_db),
         user=Depends(get_current_user)):
    existing = scoped(db, SavedQuery, request.state.org_id).filter(
        SavedQuery.user_id == user.id,
        SavedQuery.name == payload.name,
    ).first()
    if existing:
        raise HTTPException(409, "Saved query name already exists")
    row = SavedQuery(org_id=request.state.org_id, user_id=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _saved_out(row)


@router.patch("/saved/{query_id}")
def update_saved(query_id: str, payload: SavedQueryUpdateRequest, request: Request,
                 db: Session = Depends(get_db), user=Depends(get_current_user)):
    row = scoped(db, SavedQuery, request.state.org_id).filter(
        SavedQuery.id == query_id,
        SavedQuery.user_id == user.id,
    ).first()
    if not row:
        raise HTTPException(404, "Saved query not found")
    if payload.name and payload.name != row.name:
        existing = scoped(db, SavedQuery, request.state.org_id).filter(
            SavedQuery.user_id == user.id,
            SavedQuery.name == payload.name,
            SavedQuery.id != query_id,
        ).first()
        if existing:
            raise HTTPException(409, "Saved query name already exists")
        row.name = payload.name
    if payload.nl_query:
        row.nl_query = payload.nl_query
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _saved_out(row)


@router.post("/saved/{query_id}/run")
def run_saved(query_id: str, request: Request, db: Session = Depends(get_db),
              user=Depends(get_current_user)):
    from app.engines.grounded_assistant import grounded_query

    row = scoped(db, SavedQuery, request.state.org_id).filter(
        SavedQuery.id == query_id,
        SavedQuery.user_id == user.id,
    ).first()
    if not row:
        raise HTTPException(404, "Saved query not found")
    result = grounded_query(row.nl_query, request.state.org_id, db)
    row.run_count += 1
    row.last_run_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    log_activity(db, request.state.org_id, user.id, "query_run", None, 600, {"question": row.nl_query, "saved_query_id": str(row.id)})
    publish_event(
        db,
        org_id=request.state.org_id,
        actor_id=user.id,
        event_type="assistant.saved_query.answered",
        aggregate_type="saved_query",
        aggregate_id=str(row.id),
        source_module="query",
        payload={
            "question": row.nl_query,
            "provider": result["provider"],
            "confidence": result["confidence"],
            "row_count": result["row_count"],
            "source_count": result["grounding"]["source_count"],
        },
    )
    db.commit()
    return result


@router.delete("/saved/{query_id}", status_code=204)
def delete_saved(query_id: str, request: Request, db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    row = scoped(db, SavedQuery, request.state.org_id).filter(
        SavedQuery.id == query_id, SavedQuery.user_id == user.id
    ).first()
    if not row:
        raise HTTPException(404, "Saved query not found")
    db.delete(row)
    db.commit()
