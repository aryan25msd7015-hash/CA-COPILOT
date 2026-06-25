import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.system import OrganizationAgentState, SystemEvent


def publish_event(
    db: Session,
    *,
    org_id,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    source_module: str,
    actor_id=None,
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    status: str = "recorded",
) -> SystemEvent:
    event = SystemEvent(
        org_id=org_id,
        actor_id=actor_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=str(aggregate_id),
        source_module=source_module,
        status=status,
        correlation_id=correlation_id or str(uuid.uuid4()),
        causation_id=causation_id,
        payload=payload or {},
    )
    db.add(event)
    state = db.query(OrganizationAgentState).filter(OrganizationAgentState.org_id == org_id).first()
    if state:
        state.last_event = event_type
        state.updated_at = datetime.now(timezone.utc)
    return event


def mark_event_dispatched(db: Session, event: SystemEvent) -> None:
    event.status = "dispatched"
    event.dispatch_attempts = (event.dispatch_attempts or 0) + 1
    event.dispatched_at = datetime.now(timezone.utc)
    event.last_error = None


def mark_event_failed(db: Session, event: SystemEvent, error: str) -> None:
    event.status = "failed"
    event.dispatch_attempts = (event.dispatch_attempts or 0) + 1
    event.last_error = error[:2000]
