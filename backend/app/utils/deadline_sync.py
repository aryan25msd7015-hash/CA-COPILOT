"""Keep the legacy deadline list and advanced client calendar aligned."""
from app.engines.automation_engines import FILING_MATRIX, FILING_NAMES, compute_deadline, month_period
from app.models.compliance_deadline import ComplianceDeadline
from app.models.extensions import DeadlineClientMap


def seed_client_applicability(db, client, period=None):
    target = period or month_period()
    created = 0
    for filing in FILING_MATRIX.get(client.entity_type or "pvt_ltd", []):
        filing_name = FILING_NAMES.get(filing, filing)
        deadline = compute_deadline(filing, target)
        calendar_row = db.query(DeadlineClientMap).filter(
            DeadlineClientMap.client_id == client.id,
            DeadlineClientMap.filing_type == filing,
            DeadlineClientMap.period == target,
        ).first()
        if not calendar_row:
            db.add(DeadlineClientMap(
                org_id=client.org_id, client_id=client.id, filing_type=filing,
                filing_name=filing_name, period=target, deadline=deadline,
            ))
            created += 1

        legacy_row = db.query(ComplianceDeadline).filter(
            ComplianceDeadline.client_id == client.id,
            ComplianceDeadline.filing_type == filing,
            ComplianceDeadline.period == target,
        ).first()
        if not legacy_row:
            db.add(ComplianceDeadline(
                org_id=client.org_id, client_id=client.id, filing_type=filing,
                filing_name=filing_name, period=target, deadline=deadline,
            ))
    return created
