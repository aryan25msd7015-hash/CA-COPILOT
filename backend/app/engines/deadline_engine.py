"""Smart deadline engine — behavioral alert window computation."""
import logging
from datetime import date

logger = logging.getLogger(__name__)


def compute_days_before_alert(client_id: str, filing_type: str, db) -> int:
    """Return how many days before deadline to send the first reminder."""
    from app.models.compliance_deadline import ComplianceDeadline

    history = (db.query(ComplianceDeadline)
               .filter(
                   ComplianceDeadline.client_id == client_id,
                   ComplianceDeadline.filing_type == filing_type,
                   ComplianceDeadline.status.in_(["filed", "missed"]),
               )
               .order_by(ComplianceDeadline.deadline.desc())
               .limit(12).all())

    if len(history) < 3:
        return 7  # default

    avg_days_late = sum(
        max(0, (h.filed_at.date() - h.deadline).days if h.filed_at else 5)
        for h in history
    ) / len(history)

    if avg_days_late >= 5:
        return 12  # chronic late filer
    if avg_days_late >= 2:
        return 9   # sometimes late
    return 5       # usually on time


def deadline_health_component(client_id: str, db) -> float:
    """Returns 0.0–1.0 on-time filing rate for last 12 filings."""
    from app.models.compliance_deadline import ComplianceDeadline

    last_12 = (db.query(ComplianceDeadline)
               .filter(
                   ComplianceDeadline.client_id == client_id,
                   ComplianceDeadline.status.in_(["filed", "missed"]),
               )
               .order_by(ComplianceDeadline.deadline.desc())
               .limit(12).all())

    if not last_12:
        return 1.0

    on_time = sum(
        1 for h in last_12
        if h.status == "filed" and h.filed_at and h.filed_at.date() <= h.deadline
    )
    return round(on_time / len(last_12), 3)
