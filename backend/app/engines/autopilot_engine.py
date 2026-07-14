"""Exception-first automation for CA review workflows."""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.anomaly_flag import AnomalyFlag
from app.models.autopilot import AutopilotException, AutopilotFollowup, AutopilotSyncRun
from app.models.client import Client
from app.models.compliance_deadline import ComplianceDeadline
from app.models.extensions import (
    CertificateRecord, DeadlineClientMap, LeaseRecord, MsmePaymentViolation,
    RfpBid, SecretarialDocument, TimesheetEntry, UserActivityLog,
)
from app.models.reconciliation import ReconciliationResult
from app.models.transaction import Transaction
from app.utils.scoped_query import scoped

SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}
ACTIVE_STATUSES = ("open", "in_review")
MANAGED_SOURCE_TYPES = {
    "gst_reconciliation", "msme_43bh", "anomaly", "deadline", "certificate_review",
    "secretarial_review", "lease_review", "rfp_review", "tally_transaction",
    "profitability",
}

TALLY_FIELD_MAP = {
    "Voucher No": "invoice_no",
    "Voucher Number": "invoice_no",
    "Vch No.": "invoice_no",
    "Invoice No": "invoice_no",
    "Invoice Number": "invoice_no",
    "Bill No": "invoice_no",
    "Bill Number": "invoice_no",
    "Date": "date",
    "Vch Date": "date",
    "Voucher Date": "date",
    "Party Name": "vendor_name",
    "Particulars": "vendor_name",
    "Ledger Name": "vendor_name",
    "Supplier": "vendor_name",
    "GSTIN/UIN of Party": "vendor_gstin",
    "Party GSTIN": "vendor_gstin",
    "GSTIN": "vendor_gstin",
    "Amount": "amount",
    "Debit": "amount",
    "Taxable Amount": "amount",
    "Gross Amount": "amount",
    "Tax Amount": "tax_amount",
    "GST Amount": "tax_amount",
}


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _amount(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("INR", "").replace("Rs.", "").replace("Rs", "").strip()
    text = re.sub(r"[^\d.\-]", "", text)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _severity(score: float) -> str:
    if score >= 8:
        return "critical"
    if score >= 6:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def _candidate(**values) -> dict[str, Any]:
    values.setdefault("impact_amount", 0)
    values.setdefault("due_date", None)
    values.setdefault("evidence", {})
    values.setdefault("recommended_actions", [])
    return values


def _source_id(value: Any) -> Any:
    return getattr(value, "id", value)


def normalize_tally_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize Tally-style JSON rows into platform transaction rows."""
    normalized: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for index, raw in enumerate(records):
        row: dict[str, Any] = {}
        for key, value in raw.items():
            canonical = TALLY_FIELD_MAP.get(key, key)
            row[canonical] = value
        amount = _amount(row.get("amount"))
        txn_date = _date(row.get("date"))
        invoice_no = str(row.get("invoice_no") or "").strip()
        if amount is None or not txn_date or not invoice_no:
            failed.append({"index": index, "raw": raw, "reason": "invoice_no, amount and date are required"})
            continue
        row["invoice_no"] = invoice_no.upper()
        row["vendor_name"] = str(row.get("vendor_name") or "").strip() or None
        row["vendor_gstin"] = str(row.get("vendor_gstin") or "").strip().upper() or None
        row["amount"] = round(amount, 2)
        row["tax_amount"] = _amount(row.get("tax_amount"))
        row["date"] = txn_date
        normalized.append(row)
    return normalized, failed


def transaction_fingerprint(org_id: str, client_id: str, source_name: str, row: dict[str, Any]) -> str:
    key = "|".join([
        str(org_id), str(client_id), source_name or "tally",
        str(row.get("invoice_no") or ""),
        str(row.get("vendor_gstin") or ""),
        str(row.get("amount") or ""),
        str(row.get("date") or ""),
    ])
    return hashlib.sha256(key.encode()).hexdigest()


def import_tally_records(
    db: Session,
    org_id: str,
    client_id: str,
    records: list[dict[str, Any]],
    source_name: str = "TallyPrime",
    period: str | None = None,
    user_id: str | None = None,
) -> tuple[AutopilotSyncRun, list[dict[str, Any]]]:
    normalized, failed = normalize_tally_records(records)
    run = AutopilotSyncRun(
        org_id=org_id, client_id=client_id, source="tally_connector",
        source_name=source_name, period=period, status="processing",
        records_received=len(records), records_failed=len(failed), created_by=user_id,
        summary={"failed": failed[:25]},
    )
    db.add(run)
    imported = 0
    for row in normalized:
        fingerprint = transaction_fingerprint(org_id, client_id, source_name, row)
        txn = scoped(db, Transaction, org_id).filter(Transaction.fingerprint == fingerprint).first()
        if not txn:
            txn = Transaction(
                org_id=org_id, client_id=client_id, source="tally",
                fingerprint=fingerprint, match_status="unmatched",
            )
            db.add(txn)
            imported += 1
        txn.invoice_no = row["invoice_no"]
        txn.vendor_name = row.get("vendor_name")
        txn.vendor_gstin = row.get("vendor_gstin")
        txn.amount = row["amount"]
        txn.tax_amount = row.get("tax_amount")
        txn.date = row["date"]
        if 45000 <= row["amount"] < 50000:
            txn.anomaly_score = max(_num(txn.anomaly_score), 0.72)
            txn.fraud_flag = "Potential threshold gaming: invoice value is just below INR 50,000"
    run.records_imported = imported
    run.status = "completed" if not failed else "completed_with_errors"
    run.completed_at = datetime.now(timezone.utc)
    run.summary = {
        "source_name": source_name,
        "period": period,
        "failed": failed[:25],
        "threshold_flags": sum(1 for row in normalized if 45000 <= row["amount"] < 50000),
    }
    return run, failed


def build_exception_candidates(
    db: Session,
    org_id: str,
    client_id: str | None = None,
    today: date | None = None,
) -> list[dict[str, Any]]:
    today = today or date.today()
    candidates: list[dict[str, Any]] = []
    clients = scoped(db, Client, org_id).all()
    if client_id:
        clients = [client for client in clients if str(client.id) == str(client_id)]
    client_map = {str(client.id): client for client in clients}
    client_ids = set(client_map)

    def in_scope(row_client_id) -> bool:
        return str(row_client_id) in client_ids

    for row in scoped(db, ReconciliationResult, org_id).all():
        if not in_scope(row.client_id):
            continue
        mismatch = _num(row.mismatch_value)
        unmatched = int(row.unmatched_count or 0)
        if mismatch <= 0 and unmatched <= 0:
            continue
        client = client_map[str(row.client_id)]
        score = min(10, 3 + mismatch / 25000 + unmatched)
        candidates.append(_candidate(
            fingerprint=f"gst_reconciliation:{row.id}",
            source_type="gst_reconciliation",
            source_id=row.id,
            client_id=row.client_id,
            title=f"GST reconciliation variance for {client.name}",
            description=f"{unmatched} purchase records remain unmatched with a mismatch exposure of INR {mismatch:,.0f}.",
            severity=_severity(score),
            impact_amount=mismatch,
            evidence={
                "period": row.period,
                "total_purchase": _num(row.total_purchase),
                "total_gstr2b": _num(row.total_gstr2b),
                "matched_count": row.matched_count,
                "unmatched_count": row.unmatched_count,
                "module_url": f"/reconciliation?client_id={row.client_id}",
            },
            recommended_actions=[
                {"label": "Review unmatched invoices", "action_type": "review_reconciliation"},
                {"label": "Ask client for missing GSTR-2B/purchase support", "action_type": "send_followup"},
            ],
        ))

    for row in scoped(db, MsmePaymentViolation, org_id).filter(MsmePaymentViolation.status == "open").all():
        if not in_scope(row.client_id):
            continue
        client = client_map[str(row.client_id)]
        impact = _num(row.disallowance_amount) + _num(row.interest_amount)
        score = min(10, 5 + _num(row.disallowance_amount) / 100000 + int(row.days_overdue or 0) / 10)
        candidates.append(_candidate(
            fingerprint=f"msme_43bh:{row.id}",
            source_type="msme_43bh",
            source_id=row.id,
            client_id=row.client_id,
            title=f"MSME 43B(h) disallowance risk for {client.name}",
            description=f"Invoice dated {row.invoice_date} is {row.days_overdue} days overdue beyond the MSME payment window.",
            severity=_severity(score),
            impact_amount=impact,
            due_date=row.due_date,
            evidence={
                "invoice_id": str(row.invoice_id),
                "vendor_id": str(row.vendor_id),
                "invoice_amount": _num(row.invoice_amount),
                "disallowance_amount": _num(row.disallowance_amount),
                "interest_amount": _num(row.interest_amount),
                "fy": row.fy,
                "rule": "Income-tax Act Section 43B(h) / MSMED payment window",
                "module_url": f"/msme?client_id={row.client_id}",
            },
            recommended_actions=[
                {"label": "Confirm payment date and vendor MSME status", "action_type": "request_evidence"},
                {"label": "Export Clause 22 working", "action_type": "export_workpaper"},
            ],
        ))

    for flag in scoped(db, AnomalyFlag, org_id).filter(AnomalyFlag.reviewed.is_(False)).all():
        if not in_scope(flag.client_id):
            continue
        client = client_map[str(flag.client_id)]
        score = _num(flag.risk_score) * 10
        candidates.append(_candidate(
            fingerprint=f"anomaly:{flag.id}",
            source_type="anomaly",
            source_id=flag.id,
            client_id=flag.client_id,
            title=f"High-risk transaction anomaly for {client.name}",
            description=f"{flag.flag_type.replace('_', ' ').title()} requires review before audit closure.",
            severity=_severity(score),
            impact_amount=_num((flag.details or {}).get("amount")),
            evidence={
                "transaction_id": str(flag.transaction_id) if flag.transaction_id else None,
                "risk_score": _num(flag.risk_score),
                "details": flag.details or {},
                "module_url": "/anomalies",
            },
            recommended_actions=[
                {"label": "Inspect voucher evidence", "action_type": "inspect_transaction"},
                {"label": "Mark anomaly reviewed after CA conclusion", "action_type": "approve_exception"},
            ],
        ))

    deadline_rows = scoped(db, DeadlineClientMap, org_id).filter(
        DeadlineClientMap.status == "pending",
        DeadlineClientMap.deadline <= today + timedelta(days=14),
    ).all()
    if not deadline_rows:
        deadline_rows = scoped(db, ComplianceDeadline, org_id).filter(
            ComplianceDeadline.status == "pending",
            ComplianceDeadline.deadline <= today + timedelta(days=14),
        ).all()
    for row in deadline_rows:
        if not in_scope(row.client_id):
            continue
        client = client_map[str(row.client_id)]
        data_received = bool(getattr(row, "data_received", False))
        risk_score = _num(getattr(row, "risk_score", 0))
        days_left = (row.deadline - today).days
        if data_received and risk_score < 6 and days_left > 3:
            continue
        score = max(risk_score, 9 if days_left <= 1 and not data_received else 6 if days_left <= 3 else 3)
        candidates.append(_candidate(
            fingerprint=f"deadline:{row.id}",
            source_type="deadline",
            source_id=row.id,
            client_id=row.client_id,
            title=f"{row.filing_name} deadline needs action for {client.name}",
            description=f"Due on {row.deadline}. Data received: {'yes' if data_received else 'no'}.",
            severity=_severity(score),
            due_date=row.deadline,
            evidence={
                "filing_type": row.filing_type,
                "period": row.period,
                "data_received": data_received,
                "risk_score": risk_score,
                "days_left": days_left,
                "module_url": "/deadlines",
            },
            recommended_actions=[
                {"label": "Send missing-data follow-up", "action_type": "send_followup"},
                {"label": "Mark data received once support arrives", "action_type": "update_deadline"},
            ],
        ))

    for row in scoped(db, CertificateRecord, org_id).filter(CertificateRecord.status.in_(["ready", "review_required", "draft"])).all():
        if not in_scope(row.client_id):
            continue
        client = client_map[str(row.client_id)]
        invalid = not bool((row.validation or {}).get("valid", row.status == "ready"))
        candidates.append(_candidate(
            fingerprint=f"certificate_review:{row.id}",
            source_type="certificate_review",
            source_id=row.id,
            client_id=row.client_id,
            title=f"Certificate awaiting CA review for {client.name}",
            description=f"{row.title} is {row.status.replace('_', ' ')}.",
            severity="high" if invalid else "medium",
            evidence={
                "cert_type": row.cert_type,
                "validation": row.validation or {},
                "module_url": "/certificates",
            },
            recommended_actions=[
                {"label": "Review validation issues", "action_type": "review_certificate"},
                {"label": "Export signed certificate draft", "action_type": "export_deliverable"},
            ],
        ))

    for row in scoped(db, SecretarialDocument, org_id).filter(SecretarialDocument.status == "draft").all():
        if in_scope(row.client_id):
            candidates.append(_candidate(
                fingerprint=f"secretarial_review:{row.id}",
                source_type="secretarial_review",
                source_id=row.id,
                client_id=row.client_id,
                title=f"Secretarial document ready for review",
                description=f"{row.doc_type.replace('_', ' ').title()} draft generated and awaiting approval.",
                severity="medium",
                evidence={"has_xml": bool(row.generated_xml), "module_url": "/secretarial"},
                recommended_actions=[{"label": "Review minutes/forms", "action_type": "review_secretarial"}],
            ))

    for row in scoped(db, LeaseRecord, org_id).filter(LeaseRecord.verified.is_(False)).all():
        if in_scope(row.client_id):
            candidates.append(_candidate(
                fingerprint=f"lease_review:{row.id}",
                source_type="lease_review",
                source_id=row.id,
                client_id=row.client_id,
                title=f"Lease schedule needs verification",
                description=f"{row.name} Ind AS 116 schedule is generated but not verified.",
                severity="medium" if not row.ibr_assumed else "high",
                impact_amount=_num((row.extracted_data or {}).get("initial_lease_liability")),
                evidence={"ibr_assumed": row.ibr_assumed, "module_url": "/leases"},
                recommended_actions=[{"label": "Verify IBR and lease term", "action_type": "review_lease"}],
            ))

    for row in scoped(db, RfpBid, org_id).filter(RfpBid.status == "generated").all():
        candidates.append(_candidate(
            fingerprint=f"rfp_review:{row.id}",
            source_type="rfp_review",
            source_id=row.id,
            client_id=None,
            title=f"RFP proposal ready for partner approval",
            description=f"{row.title} passed eligibility checks and has a generated technical bid.",
            severity="low",
            evidence={"eligibility": row.eligibility or {}, "module_url": "/rfp"},
            recommended_actions=[{"label": "Review generated proposal", "action_type": "review_rfp"}],
        ))

    for txn in scoped(db, Transaction, org_id).filter(Transaction.source == "tally").all():
        if not in_scope(txn.client_id):
            continue
        if _num(txn.anomaly_score) < 0.7 and not txn.fraud_flag:
            continue
        client = client_map[str(txn.client_id)]
        candidates.append(_candidate(
            fingerprint=f"tally_transaction:{txn.id}",
            source_type="tally_transaction",
            source_id=txn.id,
            client_id=txn.client_id,
            title=f"Tally voucher exception for {client.name}",
            description=txn.fraud_flag or "Imported Tally voucher crossed the review risk threshold.",
            severity=_severity(_num(txn.anomaly_score) * 10),
            impact_amount=_num(txn.amount),
            due_date=txn.date,
            evidence={
                "invoice_no": txn.invoice_no,
                "vendor_name": txn.vendor_name,
                "vendor_gstin": txn.vendor_gstin,
                "date": str(txn.date) if txn.date else None,
                "amount": _num(txn.amount),
                "source": txn.source,
                "module_url": "/autopilot",
            },
            recommended_actions=[
                {"label": "Ask client for voucher/support", "action_type": "send_followup"},
                {"label": "Document CA conclusion", "action_type": "approve_exception"},
            ],
        ))

    start = date(today.year, today.month, 1)
    end = date(today.year + (today.month == 12), 1 if today.month == 12 else today.month + 1, 1)
    for client in clients:
        entries = scoped(db, TimesheetEntry, org_id).filter(
            TimesheetEntry.client_id == client.id,
            TimesheetEntry.date >= start,
            TimesheetEntry.date < end,
        ).all()
        if not entries:
            continue
        revenue = sum(_num(e.hours_logged) * _num(e.billing_rate) for e in entries if e.billable)
        cost = sum(_num(e.hours_logged) * _num(e.cost_rate) for e in entries)
        margin = revenue - cost
        activity_seconds = sum(
            int(a.duration_seconds or 0)
            for a in scoped(db, UserActivityLog, org_id).filter(
                UserActivityLog.client_id == client.id,
                UserActivityLog.created_at >= start,
                UserActivityLog.created_at < end,
            ).all()
        )
        logged_seconds = sum(_num(e.hours_logged) * 3600 for e in entries)
        unlogged_hours = max(0, (activity_seconds - logged_seconds) / 3600)
        if margin >= 0 and unlogged_hours < 2:
            continue
        candidates.append(_candidate(
            fingerprint=f"profitability:{client.id}:{start.isoformat()}",
            source_type="profitability",
            source_id=None,
            client_id=client.id,
            title=f"Profitability leakage for {client.name}",
            description=f"Estimated margin is INR {margin:,.0f}; unlogged activity is {unlogged_hours:.1f} hours.",
            severity="high" if margin < 0 else "medium",
            impact_amount=abs(margin) + unlogged_hours * 1500,
            evidence={
                "month": start.strftime("%Y-%m"),
                "revenue": revenue,
                "cost": cost,
                "margin": margin,
                "unlogged_hours": round(unlogged_hours, 2),
                "module_url": "/timesheets",
            },
            recommended_actions=[
                {"label": "Review WIP and billing leakage", "action_type": "review_profitability"},
                {"label": "Create recovery invoice or revise scope", "action_type": "commercial_action"},
            ],
        ))

    return sorted(
        candidates,
        key=lambda item: (
            -SEVERITY_ORDER.get(item["severity"], 0),
            -float(item.get("impact_amount") or 0),
            item.get("due_date") or date.max,
        ),
    )


def refresh_autopilot_exceptions(
    db: Session,
    org_id: str,
    client_id: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    candidates = build_exception_candidates(db, org_id, client_id, today)
    fingerprints = {candidate["fingerprint"] for candidate in candidates}
    created = updated = skipped_closed = 0
    for candidate in candidates:
        row = scoped(db, AutopilotException, org_id).filter(
            AutopilotException.fingerprint == candidate["fingerprint"],
        ).first()
        if not row:
            row = AutopilotException(org_id=org_id, fingerprint=candidate["fingerprint"])
            db.add(row)
            created += 1
        elif row.status not in ACTIVE_STATUSES:
            skipped_closed += 1
            continue
        else:
            updated += 1
        for key in (
            "source_type", "source_id", "client_id", "title", "description", "severity",
            "impact_amount", "due_date", "evidence", "recommended_actions",
        ):
            setattr(row, key, candidate.get(key))
        row.updated_at = datetime.now(timezone.utc)

    stale_query = scoped(db, AutopilotException, org_id).filter(
        AutopilotException.status.in_(ACTIVE_STATUSES),
        AutopilotException.source_type.in_(MANAGED_SOURCE_TYPES),
    )
    if client_id:
        stale_query = stale_query.filter(AutopilotException.client_id == client_id)
    stale = 0
    for row in stale_query.all():
        if row.fingerprint not in fingerprints:
            row.status = "resolved"
            row.reviewed_at = datetime.now(timezone.utc)
            row.evidence = {**(row.evidence or {}), "auto_resolved": True}
            stale += 1
    return {
        "created": created,
        "updated": updated,
        "skipped_closed": skipped_closed,
        "auto_resolved": stale,
        "candidate_count": len(candidates),
    }


def summarize_autopilot(db: Session, org_id: str) -> dict[str, Any]:
    rows = scoped(db, AutopilotException, org_id).filter(
        AutopilotException.status.in_(ACTIVE_STATUSES),
    ).all()
    total_impact = sum(_num(row.impact_amount) for row in rows)
    by_severity = {key: 0 for key in SEVERITY_ORDER}
    by_source: dict[str, int] = {}
    urgent_due = 0
    today = date.today()
    for row in rows:
        by_severity[row.severity] = by_severity.get(row.severity, 0) + 1
        by_source[row.source_type] = by_source.get(row.source_type, 0) + 1
        if row.due_date and row.due_date <= today + timedelta(days=3):
            urgent_due += 1
    estimated_review_minutes = sum({"critical": 20, "high": 15, "medium": 8, "low": 4}.get(row.severity, 8) for row in rows)
    estimated_manual_minutes = len(rows) * 55
    time_saved_minutes = max(0, estimated_manual_minutes - estimated_review_minutes)
    action_counts: dict[str, int] = {}
    for row in rows:
        for action in row.recommended_actions or []:
            label = action.get("label") or action.get("action_type") or "Review exception"
            action_counts[label] = action_counts.get(label, 0) + 1
    top_actions = [
        {"label": label, "count": count}
        for label, count in sorted(action_counts.items(), key=lambda item: (-item[1], item[0]))[:6]
    ]
    sync_rows = scoped(db, AutopilotSyncRun, org_id).all()
    last_sync_at = max((row.started_at for row in sync_rows if row.started_at), default=None)
    stale_sync_count = sum(
        1 for row in sync_rows
        if row.started_at and row.started_at.date() < today - timedelta(days=7)
    )
    failed_sync_count = sum(1 for row in sync_rows if row.status in {"failed", "completed_with_errors"})
    followups = scoped(db, AutopilotFollowup, org_id).all()
    followup_by_status: dict[str, int] = {}
    for followup in followups:
        followup_by_status[followup.status] = followup_by_status.get(followup.status, 0) + 1
    blocked_followups = sum(
        count for status, count in followup_by_status.items()
        if status in {"blocked_no_consent", "ready_provider_missing", "failed"}
    )
    headline = "All clear"
    if rows:
        top = sorted(rows, key=lambda row: (-SEVERITY_ORDER.get(row.severity, 0), -_num(row.impact_amount)))[0]
        headline = f"{top.severity.title()} exception: {top.title}"
    return {
        "open_count": len(rows),
        "by_severity": by_severity,
        "by_source": by_source,
        "total_impact": total_impact,
        "urgent_due": urgent_due,
        "estimated_review_minutes": estimated_review_minutes,
        "time_saved_minutes": time_saved_minutes,
        "top_actions": top_actions,
        "last_sync_at": last_sync_at.isoformat() if last_sync_at else None,
        "stale_sync_count": stale_sync_count,
        "failed_sync_count": failed_sync_count,
        "followup_by_status": followup_by_status,
        "blocked_followups": blocked_followups,
        "headline": headline,
    }
