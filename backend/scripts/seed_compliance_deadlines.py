"""Seed standard deadlines for every client for the current and next FY."""
import sys
from calendar import monthrange
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models.client import Client
from app.models.compliance_deadline import ComplianceDeadline


def _safe_date(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, monthrange(year, month)[1]))


def seed() -> int:
    db = SessionLocal()
    created = 0
    try:
        start_year = date.today().year if date.today().month >= 4 else date.today().year - 1
        for client in db.query(Client).all():
            for year in (start_year, start_year + 1):
                for month_offset in range(12):
                    month = ((4 + month_offset - 1) % 12) + 1
                    filing_year = year if month >= 4 else year + 1
                    next_month = month % 12 + 1
                    next_year = filing_year + (1 if month == 12 else 0)
                    period = _safe_date(filing_year, month, 1).strftime("%b-%Y")
                    entries = [
                        ("GSTR1", "GSTR-1", _safe_date(next_year, next_month, 11), "sales_register"),
                        ("GSTR3B", "GSTR-3B", _safe_date(next_year, next_month, 20), "purchase_register"),
                    ]
                    for filing_type, name, deadline, required in entries:
                        exists = db.query(ComplianceDeadline).filter_by(
                            client_id=client.id, filing_type=filing_type, period=period
                        ).first()
                        if not exists:
                            db.add(ComplianceDeadline(
                                org_id=client.org_id, client_id=client.id, filing_type=filing_type,
                                filing_name=name, period=period, deadline=deadline, doc_required=required,
                            ))
                            created += 1
                for filing_type, name, month, day in [
                    ("ADVANCE_TAX", "Advance Tax", 6, 15), ("ADVANCE_TAX", "Advance Tax", 9, 15),
                    ("ADVANCE_TAX", "Advance Tax", 12, 15), ("ADVANCE_TAX", "Advance Tax", 3, 15),
                    ("TDS_24Q", "TDS Form 24Q", 5, 31), ("TDS_26Q", "TDS Form 26Q", 5, 31),
                ]:
                    deadline_year = year if month >= 4 else year + 1
                    period = f"FY {year}-{str(year + 1)[-2:]}"
                    exists = db.query(ComplianceDeadline).filter_by(
                        client_id=client.id, filing_type=filing_type, period=period,
                        deadline=_safe_date(deadline_year, month, day),
                    ).first()
                    if not exists:
                        db.add(ComplianceDeadline(
                            org_id=client.org_id, client_id=client.id, filing_type=filing_type,
                            filing_name=name, period=period,
                            deadline=_safe_date(deadline_year, month, day),
                        ))
                        created += 1
        db.commit()
        return created
    finally:
        db.close()


if __name__ == "__main__":
    print(f"Created {seed()} deadlines")
