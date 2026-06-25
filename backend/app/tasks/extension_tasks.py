"""Scheduled and OCR follow-up tasks for advanced automation modules."""
from datetime import datetime, timezone

from app.celery_app import celery_app
from app.database import SessionLocal
from app.engines.automation_engines import (
    deadline_risk_score, get_fy, msme_violation_values, parse_udyam_certificate,
)


@celery_app.task(queue="heavy")
def score_deadline_risks():
    from app.models.client import Client
    from app.models.extensions import DeadlineClientMap

    db = SessionLocal()
    try:
        rows = db.query(DeadlineClientMap).filter(DeadlineClientMap.status == "pending").all()
        for row in rows:
            client = db.query(Client).filter(Client.id == row.client_id).first()
            row.risk_score = deadline_risk_score(
                row.deadline, row.data_received, row.late_count_last_12m,
                row.has_open_notice, client.health_score if client else 100,
            )
        db.commit()
        return {"scored": len(rows)}
    finally:
        db.close()


@celery_app.task(queue="ocr")
def process_udyam_certificate(document_id: str):
    from app.models.document import Document
    from app.models.extensions import MsmePaymentViolation, MsmeVendor
    from app.models.transaction import Transaction

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc or not doc.ocr_text:
            return {"processed": False}
        values = parse_udyam_certificate(doc.ocr_text)
        vendor = db.query(MsmeVendor).filter(
            MsmeVendor.client_id == doc.client_id,
            MsmeVendor.vendor_gstin == values["vendor_gstin"],
        ).first()
        if not vendor:
            vendor = MsmeVendor(org_id=doc.org_id, client_id=doc.client_id)
            db.add(vendor)
        for key, value in values.items():
            setattr(vendor, key, value)
        vendor.udyam_cert_doc_id = doc.id
        vendor.verified_at = datetime.now(timezone.utc)
        db.flush()
        created = 0
        invoices = db.query(Transaction).filter(
            Transaction.client_id == doc.client_id,
            Transaction.vendor_gstin == vendor.vendor_gstin,
            Transaction.date.isnot(None), Transaction.amount.isnot(None),
        ).all()
        for invoice in invoices:
            result = msme_violation_values(invoice.date, invoice.amount)
            if not result["violated"]:
                continue
            violation = db.query(MsmePaymentViolation).filter(
                MsmePaymentViolation.vendor_id == vendor.id,
                MsmePaymentViolation.invoice_id == invoice.id,
            ).first()
            if not violation:
                violation = MsmePaymentViolation(
                    org_id=doc.org_id, client_id=doc.client_id, vendor_id=vendor.id,
                    invoice_id=invoice.id, invoice_date=invoice.date,
                    invoice_amount=invoice.amount, fy=get_fy(invoice.date),
                )
                db.add(violation)
                created += 1
            for key in ("due_date", "days_overdue", "disallowance_amount", "interest_amount"):
                setattr(violation, key, result[key])
        doc.status = "processed"
        db.commit()
        return {"processed": True, "violations_created": created}
    finally:
        db.close()
