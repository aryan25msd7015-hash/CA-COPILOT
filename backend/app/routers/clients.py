from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List

from app.database import get_db
from app.models.client import Client
from app.models.health_history import ClientHealthHistory
from app.models.system import SystemAuditLog
from app.schemas.client import ClientCreate, ClientUpdate, ClientOut, ClientListOut
from app.utils.deadline_sync import seed_client_applicability
from app.utils.deps import get_current_user, require_role
from app.utils.scoped_query import scoped
from app.utils.events import publish_event

router = APIRouter()

WORKLOAD_WEIGHTS = {
    "doc_verification": 0.5,
    "routine_filing": 1.5,
    "annual_return": 5.0,
    "notice_dispute": 8.0,
    "custom_task": 1.0,
    "overdue_deadline": 3.0,
    "failed_document": 2.0,
    "open_anomaly": 4.0,
}
MAX_SAFE_WORKLOAD_UNITS = 40.0


def _ensure_unique_gstin(db: Session, org_id, gstin: str | None, client_id: str | None = None) -> None:
    if not gstin:
        return
    query = scoped(db, Client, org_id).filter(Client.gstin == gstin)
    if client_id:
        query = query.filter(Client.id != client_id)
    if query.first():
        raise HTTPException(400, "GSTIN already exists for another client")


def _ensure_unique_pan(db: Session, org_id, pan: str | None, client_id: str | None = None) -> None:
    if not pan:
        return
    query = scoped(db, Client, org_id).filter(Client.pan == pan)
    if client_id:
        query = query.filter(Client.id != client_id)
    if query.first():
        raise HTTPException(400, "PAN already exists for another client")


def _entity_from_pan(pan: str | None) -> str | None:
    if not pan:
        return None
    return {
        "C": "company",
        "P": "individual",
        "F": "firm",
        "H": "huf",
        "T": "trust",
        "L": "local_authority",
        "A": "association_of_persons",
        "B": "body_of_individuals",
        "G": "government",
        "J": "artificial_juridical_person",
    }.get(pan[3])


def _seed_health_baseline(db: Session, client: Client) -> None:
    exists = scoped(db, ClientHealthHistory, client.org_id).filter(ClientHealthHistory.client_id == client.id).first()
    if exists:
        return
    db.add(ClientHealthHistory(
        org_id=client.org_id,
        client_id=client.id,
        score=client.health_score or 100,
        tier="green",
        components={
            "baseline": True,
            "source": "client.created",
            "client_partition": client.client_partition,
        },
    ))


def _audit_client(db: Session, request: Request, action: str, client: Client, payload: dict) -> None:
    db.add(SystemAuditLog(
        org_id=request.state.org_id,
        actor_id=request.state.user_id,
        action=action,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        payload={"client_id": str(client.id), "client_name": client.name, **payload},
    ))


@router.get("", response_model=List[ClientListOut])
def list_clients(request: Request, db: Session = Depends(get_db),
                 skip: int = 0, limit: int = 2000, search: str = "",
                 include_archived: bool = False,
                 _=Depends(get_current_user)):
    """List all clients sorted by health_score ascending (worst first)."""
    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > 5000:
        raise HTTPException(422, "limit must be between 1 and 5000")
    query = scoped(db, Client, request.state.org_id)
    if not include_archived:
        query = query.filter(Client.status == "active")
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(or_(Client.name.ilike(pattern), Client.gstin.ilike(pattern), Client.email.ilike(pattern)))
    return query.order_by(Client.health_score.asc(), Client.name.asc()).offset(skip).limit(limit).all()


@router.post("", response_model=ClientOut, status_code=201)
def create_client(req: ClientCreate, request: Request,
                  db: Session = Depends(get_db), _=Depends(require_role(["partner", "manager"]))):
    payload = req.model_dump()
    _ensure_unique_gstin(db, request.state.org_id, payload.get("gstin"))
    _ensure_unique_pan(db, request.state.org_id, payload.get("pan"))
    metadata = {
        "event": "client.created",
        "pan_entity_class": _entity_from_pan(payload.get("pan")),
        "automation_ready": True,
    }
    client = Client(org_id=request.state.org_id, status="active", lifecycle_metadata=metadata, **payload)
    db.add(client)
    db.flush()
    client.client_partition = f"org_{request.state.org_id}:client_{client.id}"
    client.lifecycle_metadata = {**metadata, "client_partition": client.client_partition}
    _seed_health_baseline(db, client)
    seed_client_applicability(db, client)
    _audit_client(db, request, "CLIENT_CREATED", client, {"event": "client.created", "partition": client.client_partition})
    publish_event(
        db,
        org_id=request.state.org_id,
        actor_id=request.state.user_id,
        event_type="client.created",
        aggregate_type="client",
        aggregate_id=str(client.id),
        source_module="clients",
        payload={"client_name": client.name, "partition": client.client_partition, "automation_ready": True},
    )
    db.commit()
    db.refresh(client)
    return client


@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_id: str, request: Request,
               db: Session = Depends(get_db), _=Depends(get_current_user)):
    client = (scoped(db, Client, request.state.org_id)
              .filter(Client.id == client_id, Client.status == "active").first())
    if not client:
        raise HTTPException(404, "Client not found")
    return client


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(client_id: str, req: ClientUpdate, request: Request,
                  db: Session = Depends(get_db), _=Depends(require_role(["partner", "manager"]))):
    client = (scoped(db, Client, request.state.org_id)
              .filter(Client.id == client_id, Client.status == "active").first())
    if not client:
        raise HTTPException(404, "Client not found")
    payload = req.model_dump(exclude_none=True)
    _ensure_unique_gstin(db, request.state.org_id, payload.get("gstin"), client_id=client_id)
    _ensure_unique_pan(db, request.state.org_id, payload.get("pan"), client_id=client_id)
    for key, val in payload.items():
        setattr(client, key, val)
    if "pan" in payload:
        client.lifecycle_metadata = {**(client.lifecycle_metadata or {}), "pan_entity_class": _entity_from_pan(client.pan)}
    db.flush()
    seed_client_applicability(db, client)
    _audit_client(db, request, "CLIENT_UPDATED", client, {"changed_fields": sorted(payload.keys())})
    publish_event(
        db,
        org_id=request.state.org_id,
        actor_id=request.state.user_id,
        event_type="client.updated",
        aggregate_type="client",
        aggregate_id=str(client.id),
        source_module="clients",
        payload={"changed_fields": sorted(payload.keys()), "client_name": client.name},
    )
    db.commit()
    db.refresh(client)
    return client


@router.delete("/{client_id}", status_code=204)
def delete_client(client_id: str, request: Request,
                  db: Session = Depends(get_db),
                  _=Depends(require_role(["partner", "manager"]))):
    client = (scoped(db, Client, request.state.org_id)
              .filter(Client.id == client_id, Client.status == "active").first())
    if not client:
        raise HTTPException(404, "Client not found")
    client.status = "archived"
    client.deleted_at = datetime.now(timezone.utc)
    client.lifecycle_metadata = {
        **(client.lifecycle_metadata or {}),
        "event": "client.archived",
        "archived_at": client.deleted_at.isoformat(),
        "automation_paused": True,
    }
    _audit_client(db, request, "CLIENT_ARCHIVED", client, {"event": "client.archived", "automation_paused": True})
    publish_event(
        db,
        org_id=request.state.org_id,
        actor_id=request.state.user_id,
        event_type="client.archived",
        aggregate_type="client",
        aggregate_id=str(client.id),
        source_module="clients",
        payload={"client_name": client.name, "automation_paused": True},
    )
    db.commit()


@router.get("/{client_id}/health-history")
def get_health_history(client_id: str, request: Request,
                       db: Session = Depends(get_db), _=Depends(get_current_user)):
    # Verify client belongs to org
    client = (scoped(db, Client, request.state.org_id)
              .filter(Client.id == client_id, Client.status == "active").first())
    if not client:
        raise HTTPException(404, "Client not found")
    history = (scoped(db, ClientHealthHistory, request.state.org_id)
               .filter(ClientHealthHistory.client_id == client_id)
               .order_by(ClientHealthHistory.computed_at.desc())
               .limit(30).all())
    return [
        {"score": h.score, "tier": h.tier, "components": h.components,
         "computed_at": h.computed_at}
        for h in history
    ]


@router.get("/{client_id}/summary")
def get_client_summary(client_id: str, request: Request,
                       db: Session = Depends(get_db), _=Depends(get_current_user)):
    from app.models.anomaly_flag import AnomalyFlag
    from app.models.compliance_deadline import ComplianceDeadline
    from app.models.document import Document
    from app.models.health_history import ClientHealthHistory
    from app.models.extensions import TimesheetEntry
    from app.models.practice_ops import BillingPlan, ClientPortalContact, PortalRequest, PracticeInvoice, PracticeTask
    from app.models.transaction import Transaction

    client = scoped(db, Client, request.state.org_id).filter(Client.id == client_id, Client.status == "active").first()
    if not client:
        raise HTTPException(404, "Client not found")

    today = date.today()
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    forty_eight_hours = today + timedelta(days=2)

    document_counts = dict(
        scoped(db, Document, request.state.org_id)
        .filter(Document.client_id == client_id, Document.created_at >= thirty_days_ago)
        .with_entities(Document.status, func.count(Document.id))
        .group_by(Document.status)
        .all()
    )
    notice_counts = dict(
        scoped(db, Document, request.state.org_id)
        .filter(Document.client_id == client_id, Document.doc_type == "notice")
        .with_entities(Document.status, func.count(Document.id))
        .group_by(Document.status)
        .all()
    )
    deadlines = (
        scoped(db, ComplianceDeadline, request.state.org_id)
        .filter(ComplianceDeadline.client_id == client_id, ComplianceDeadline.status != "filed")
        .order_by(ComplianceDeadline.deadline.asc())
        .limit(8)
        .all()
    )
    overdue_deadlines = (
        scoped(db, ComplianceDeadline, request.state.org_id)
        .filter(ComplianceDeadline.client_id == client_id, ComplianceDeadline.status != "filed", ComplianceDeadline.deadline < today)
        .count()
    )
    due_48h_deadlines = (
        scoped(db, ComplianceDeadline, request.state.org_id)
        .filter(
            ComplianceDeadline.client_id == client_id,
            ComplianceDeadline.status != "filed",
            ComplianceDeadline.deadline >= today,
            ComplianceDeadline.deadline <= forty_eight_hours,
        )
        .count()
    )
    transactions = (
        scoped(db, Transaction, request.state.org_id)
        .filter(Transaction.client_id == client_id)
        .order_by(Transaction.created_at.desc())
        .limit(10)
        .all()
    )
    open_anomalies = (
        scoped(db, AnomalyFlag, request.state.org_id)
        .filter(AnomalyFlag.client_id == client_id, AnomalyFlag.reviewed.is_(False))
        .count()
    )
    transaction_total = scoped(db, Transaction, request.state.org_id).filter(Transaction.client_id == client_id).count()
    unreconciled_transactions = (
        scoped(db, Transaction, request.state.org_id)
        .filter(Transaction.client_id == client_id, Transaction.match_status == "unmatched")
        .count()
    )
    open_tasks = (
        scoped(db, PracticeTask, request.state.org_id)
        .filter(PracticeTask.client_id == client_id, PracticeTask.status.in_(["open", "in_progress"]))
        .count()
    )
    tasks_by_service = dict(
        scoped(db, PracticeTask, request.state.org_id)
        .filter(PracticeTask.client_id == client_id, PracticeTask.status.in_(["open", "in_progress"]))
        .with_entities(PracticeTask.service_type, func.count(PracticeTask.id))
        .group_by(PracticeTask.service_type)
        .all()
    )
    timesheet_hours = (
        scoped(db, TimesheetEntry, request.state.org_id)
        .filter(TimesheetEntry.client_id == client_id, TimesheetEntry.date >= today.replace(day=1))
        .with_entities(func.coalesce(func.sum(TimesheetEntry.hours_logged), 0))
        .scalar()
    )
    portal_open_requests = (
        scoped(db, PortalRequest, request.state.org_id)
        .filter(PortalRequest.client_id == client_id, PortalRequest.status.in_(["requested", "in_progress"]))
        .count()
    )
    portal_contacts = scoped(db, ClientPortalContact, request.state.org_id).filter(ClientPortalContact.client_id == client_id).count()
    active_billing_plans = scoped(db, BillingPlan, request.state.org_id).filter(BillingPlan.client_id == client_id, BillingPlan.active.is_(True)).count()
    unpaid_invoices = (
        scoped(db, PracticeInvoice, request.state.org_id)
        .filter(PracticeInvoice.client_id == client_id, PracticeInvoice.status.in_(["sent", "overdue", "part_paid"]))
        .count()
    )
    latest_health = (
        scoped(db, ClientHealthHistory, request.state.org_id)
        .filter(ClientHealthHistory.client_id == client_id)
        .order_by(ClientHealthHistory.computed_at.desc())
        .first()
    )
    unreconciled_ratio = round((unreconciled_transactions / transaction_total) * 100, 2) if transaction_total else 0
    friction_index = min(100, round(
        (open_tasks * 4)
        + (overdue_deadlines * 12)
        + (open_anomalies * 8)
        + ((document_counts.get("ocr_failed", 0) + document_counts.get("parse_failed", 0)) * 6)
        + (unreconciled_ratio * 0.5)
    ))
    health_score = latest_health.score if latest_health else client.health_score
    status_indicator = "critical" if health_score < 50 or overdue_deadlines else "watch" if health_score < 75 or friction_index > 40 else "stable"
    compiled_at = datetime.now(timezone.utc).isoformat()
    agent_context = (
        f"{client.name} has health score {health_score}/100 and is {status_indicator}. "
        f"There are {overdue_deadlines} overdue deadlines, {due_48h_deadlines} due within 48 hours, "
        f"{open_anomalies} open anomaly flags, {document_counts.get('ocr_failed', 0) + document_counts.get('parse_failed', 0)} failed document pipeline items, "
        f"and {unreconciled_ratio}% unreconciled transactions. Friction index is {friction_index}/100."
    )
    return {
        "metadata": {
            "client_id": client_id,
            "organization_id": str(request.state.org_id),
            "compiled_at": compiled_at,
            "ttl_seconds": 3600,
            "cache_key": f"cache:org:{request.state.org_id}:client:{client_id}:summary",
            "materialized": False,
        },
        "health_matrix": {
            "current_score": health_score,
            "latest_tier": latest_health.tier if latest_health else None,
            "status_indicator": status_indicator,
            "friction_index": friction_index,
        },
        "document_metrics": {
            "last_30_days": {
                "pending": document_counts.get("pending", 0),
                "processing": document_counts.get("pending", 0),
                "ocr_complete": document_counts.get("ocr_complete", 0),
                "processed": document_counts.get("processed", 0),
                "failed": document_counts.get("ocr_failed", 0) + document_counts.get("parse_failed", 0),
            },
            "notice_documents": notice_counts,
        },
        "deadline_metrics": {
            "open": len(deadlines),
            "overdue": overdue_deadlines,
            "due_in_48h": due_48h_deadlines,
        },
        "reconciliation_metrics": {
            "transaction_count": transaction_total,
            "unreconciled_count": unreconciled_transactions,
            "unreconciled_ratio": unreconciled_ratio,
        },
        "workload_vectors": {
            "open_tasks": open_tasks,
            "tasks_by_service": tasks_by_service,
            "current_month_hours": float(timesheet_hours or 0),
            "portal_open_requests": portal_open_requests,
            "portal_contacts": portal_contacts,
        },
        "billing_metrics": {
            "active_plans": active_billing_plans,
            "unpaid_invoices": unpaid_invoices,
        },
        "agent_context": agent_context,
        "open_anomaly_count": open_anomalies,
        "upcoming_deadlines": [
            {
                "id": str(row.id), "filing_name": row.filing_name,
                "period": row.period, "deadline": str(row.deadline), "status": row.status,
            }
            for row in deadlines
        ],
        "recent_transactions": [
            {
                "id": str(row.id), "invoice_no": row.invoice_no,
                "vendor_name": row.vendor_name, "amount": float(row.amount or 0),
                "date": str(row.date) if row.date else None,
                "match_status": row.match_status,
                "anomaly_score": float(row.anomaly_score) if row.anomaly_score is not None else None,
            }
            for row in transactions
        ],
    }


@router.get("/workload/distribution")
def client_workload_distribution(request: Request, db: Session = Depends(get_db),
                                 _=Depends(get_current_user)):
    from app.models.anomaly_flag import AnomalyFlag
    from app.models.compliance_deadline import ComplianceDeadline
    from app.models.document import Document
    from app.models.practice_ops import PracticeTask
    from app.models.user import User

    today = date.today()
    clients = scoped(db, Client, request.state.org_id).filter(Client.status == "active").all()
    users = scoped(db, User, request.state.org_id).filter(User.status == "active").all()
    user_map = {str(user.id): user.email for user in users}
    active_task_statuses = ["open", "in_progress", "review", "blocked"]

    client_rows = []
    team_load: dict[str, dict] = {
        str(user.id): {
            "user_id": str(user.id),
            "email": user.email,
            "total_units": 0.0,
            "assigned_clients": set(),
            "open_task_count": 0,
        }
        for user in users
    }

    for client in clients:
        tasks = scoped(db, PracticeTask, request.state.org_id).filter(
            PracticeTask.client_id == client.id,
            PracticeTask.status.in_(active_task_statuses),
        ).all()
        overdue_deadlines = scoped(db, ComplianceDeadline, request.state.org_id).filter(
            ComplianceDeadline.client_id == client.id,
            ComplianceDeadline.status != "filed",
            ComplianceDeadline.deadline < today,
        ).count()
        pending_deadlines = scoped(db, ComplianceDeadline, request.state.org_id).filter(
            ComplianceDeadline.client_id == client.id,
            ComplianceDeadline.status != "filed",
        ).count()
        failed_documents = scoped(db, Document, request.state.org_id).filter(
            Document.client_id == client.id,
            Document.status.in_(["ocr_failed", "parse_failed"]),
        ).count()
        pending_documents = scoped(db, Document, request.state.org_id).filter(
            Document.client_id == client.id,
            Document.status == "pending",
        ).count()
        open_anomalies = scoped(db, AnomalyFlag, request.state.org_id).filter(
            AnomalyFlag.client_id == client.id,
            AnomalyFlag.reviewed.is_(False),
        ).count()

        task_units = 0.0
        task_breakdown: dict[str, int] = {}
        assignees: dict[str, float] = {}
        for task in tasks:
            service_type = task.service_type or "custom_task"
            weight = WORKLOAD_WEIGHTS.get(service_type, WORKLOAD_WEIGHTS["custom_task"])
            priority_multiplier = {"low": 0.8, "medium": 1.0, "high": 1.4, "urgent": 1.8}.get(task.priority, 1.0)
            units = round(weight * priority_multiplier, 2)
            task_units += units
            task_breakdown[service_type] = task_breakdown.get(service_type, 0) + 1
            if task.assigned_to:
                user_id = str(task.assigned_to)
                assignees[user_id] = assignees.get(user_id, 0) + units
                team_load.setdefault(user_id, {
                    "user_id": user_id,
                    "email": user_map.get(user_id, ""),
                    "total_units": 0.0,
                    "assigned_clients": set(),
                    "open_task_count": 0,
                })
                team_load[user_id]["total_units"] += units
                team_load[user_id]["assigned_clients"].add(str(client.id))
                team_load[user_id]["open_task_count"] += 1

        complexity = round(
            task_units
            + overdue_deadlines * WORKLOAD_WEIGHTS["overdue_deadline"]
            + failed_documents * WORKLOAD_WEIGHTS["failed_document"]
            + open_anomalies * WORKLOAD_WEIGHTS["open_anomaly"]
            + pending_documents * WORKLOAD_WEIGHTS["doc_verification"],
            2,
        )
        suggested_owner = min(team_load.values(), key=lambda row: row["total_units"], default=None)
        client_rows.append({
            "client_id": str(client.id),
            "client_name": client.name,
            "health_score": client.health_score,
            "complexity_index": complexity,
            "risk_band": "high" if complexity >= 30 or client.health_score < 50 else "medium" if complexity >= 15 or client.health_score < 75 else "low",
            "pending_deadlines": pending_deadlines,
            "overdue_deadlines": overdue_deadlines,
            "failed_documents": failed_documents,
            "pending_documents": pending_documents,
            "open_anomalies": open_anomalies,
            "open_tasks": len(tasks),
            "task_breakdown": task_breakdown,
            "assignee_units": [
                {"user_id": user_id, "email": user_map.get(user_id, ""), "units": round(units, 2)}
                for user_id, units in assignees.items()
            ],
            "routing_suggestion": {
                "suggested_user_id": suggested_owner["user_id"] if suggested_owner else None,
                "suggested_email": suggested_owner["email"] if suggested_owner else None,
                "reason": "lowest_current_load" if suggested_owner else "no_assigned_workload_data",
            },
        })

    team_rows = []
    for user_id, row in team_load.items():
        units = round(row["total_units"], 2)
        team_rows.append({
            "user_id": user_id,
            "email": row["email"],
            "total_units": units,
            "capacity_limit": MAX_SAFE_WORKLOAD_UNITS,
            "utilization_pct": round((units / MAX_SAFE_WORKLOAD_UNITS) * 100, 2),
            "assigned_clients": sorted(row["assigned_clients"]),
            "open_task_count": row["open_task_count"],
            "status": "overloaded" if units > MAX_SAFE_WORKLOAD_UNITS else "balanced",
        })

    loads = [row["total_units"] for row in team_rows]
    mean_load = sum(loads) / len(loads) if loads else 0
    variance = sum((value - mean_load) ** 2 for value in loads) / len(loads) if loads else 0
    std_dev = round(variance ** 0.5, 2)
    overloaded = [row for row in team_rows if row["total_units"] > MAX_SAFE_WORKLOAD_UNITS]

    return {
        "organization_id": str(request.state.org_id),
        "compiled_at": datetime.now(timezone.utc).isoformat(),
        "weights": WORKLOAD_WEIGHTS,
        "client_workload_complexities": sorted(client_rows, key=lambda row: row["complexity_index"], reverse=True),
        "team_utilization_profiles": sorted(team_rows, key=lambda row: row["total_units"], reverse=True),
        "distribution_anomalies": {
            "is_imbalanced": bool(overloaded) or std_dev >= 12,
            "std_dev_units": std_dev,
            "mean_units": round(mean_load, 2),
            "overloaded_resource_count": len(overloaded),
            "bottleneck_details": overloaded,
        },
    }
