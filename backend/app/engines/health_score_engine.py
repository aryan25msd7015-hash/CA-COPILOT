"""Client health score engine — 5-component 0–100 composite score."""
import logging
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def get_itc_gap_pct(client_id: str, db: Session) -> float:
    from app.models.reconciliation import ReconciliationResult
    result = (db.query(ReconciliationResult)
              .filter(ReconciliationResult.client_id == client_id)
              .order_by(ReconciliationResult.run_at.desc())
              .first())
    if not result or not result.total_purchase or result.total_purchase == 0:
        return 0.0
    mismatch = float(result.mismatch_value or 0)
    total = float(result.total_purchase)
    return min(1.0, mismatch / total)


def get_open_notices_count(client_id: str, db: Session) -> int:
    from app.models.document import Document
    return db.query(Document).filter(
        Document.client_id == client_id,
        Document.doc_type == "notice",
        Document.status != "processed",
    ).count()


def get_anomaly_rate(client_id: str, db: Session) -> float:
    from app.models.transaction import Transaction
    from datetime import date, timedelta
    three_months_ago = date.today() - timedelta(days=90)
    total = db.query(Transaction).filter(
        Transaction.client_id == client_id,
        Transaction.date >= three_months_ago,
    ).count()
    if total == 0:
        return 0.0
    flagged = db.query(Transaction).filter(
        Transaction.client_id == client_id,
        Transaction.date >= three_months_ago,
        Transaction.anomaly_score >= 0.7,
    ).count()
    return flagged / total


def get_tds_compliance_rate(client_id: str, db: Session) -> float:
    from app.models.compliance_deadline import ComplianceDeadline
    tds_deadlines = db.query(ComplianceDeadline).filter(
        ComplianceDeadline.client_id == client_id,
        ComplianceDeadline.filing_type.in_(["TDS_24Q", "TDS_26Q"]),
        ComplianceDeadline.status.in_(["filed", "missed"]),
    ).limit(12).all()
    if not tds_deadlines:
        return 1.0
    on_time = sum(
        1 for d in tds_deadlines
        if d.status == "filed" and d.filed_at and d.filed_at.date() <= d.deadline
    )
    return on_time / len(tds_deadlines)


def compute_health_score(client_id: str, db: Session) -> dict:
    """Compute 0–100 health score from 5 components."""
    from app.engines.deadline_engine import deadline_health_component

    gst_rate     = deadline_health_component(client_id, db)
    itc_gap_pct  = get_itc_gap_pct(client_id, db)
    open_notices = get_open_notices_count(client_id, db)
    anomaly_rate = get_anomaly_rate(client_id, db)
    tds_rate     = get_tds_compliance_rate(client_id, db)

    gst_score     = round(gst_rate * 25, 2)
    itc_score     = round(max(0.0, 25.0 * (1.0 - min(itc_gap_pct * 5, 1.0))), 2)
    notice_score  = round(max(0.0, 25.0 - open_notices * 8), 2)
    anomaly_score = round(max(0.0, 15.0 * (1.0 - min(anomaly_rate * 10, 1.0))), 2)
    tds_score     = round(tds_rate * 10, 2)

    total = round(gst_score + itc_score + notice_score + anomaly_score + tds_score)
    tier  = "green" if total >= 75 else "amber" if total >= 50 else "red"

    return {
        "score": total,
        "tier": tier,
        "components": {
            "gst":     gst_score,
            "itc":     itc_score,
            "notices": notice_score,
            "anomaly": anomaly_score,
            "tds":     tds_score,
        },
    }
