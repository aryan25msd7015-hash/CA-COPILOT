"""Populate the verified demo account with representative cross-module data."""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models.anomaly_flag import AnomalyFlag
from app.models.client import Client
from app.models.compliance_deadline import ComplianceDeadline
from app.models.document import Document
from app.models.health_history import ClientHealthHistory
from app.models.organization import Organization
from app.models.reconciliation import ReconciliationResult
from app.models.transaction import Transaction
from app.models.user import User
from app.models.whatsapp_reminder import WhatsAppReminder
from app.models.autopilot import AutopilotSyncRun
from app.models.extensions import (
    BankFacility, CertificateRecord, DeadlineClientMap, DebtorItem,
    DrawingPowerStatement, FirmCredential, InventoryItem, LeaseRecord,
    MsmePaymentViolation, MsmeVendor, RfpBid, SecretarialDocument,
    TimesheetEntry, UserActivityLog,
)
from app.routers.auth import pwd_ctx
from app.utils.deadline_sync import seed_client_applicability
from app.engines.automation_engines import (
    CERTIFICATE_TYPES, FILING_NAMES, compute_lease_schedule, extract_lease_data,
    generate_bid_proposal, generate_secretarial_document, get_fy,
    check_rfp_eligibility, deadline_risk_score, msme_violation_values,
)
from app.engines.autopilot_engine import refresh_autopilot_exceptions

DEMO_EMAIL = "demo@cacopilot.in"
DEMO_PASSWORD = "DemoPass@2026"
DEMO_RATIOS = {
    "current_ratio": 1.72,
    "debt_equity_ratio": 1.05,
    "gross_margin_pct": 30.5,
    "asset_turnover": 1.58,
}


def get_or_create_client(db, org, name, **values):
    client = db.query(Client).filter(Client.org_id == org.id, Client.name == name).first()
    if not client:
        client = Client(org_id=org.id, name=name, **values)
        db.add(client)
        db.flush()
    else:
        for key, value in values.items():
            setattr(client, key, value)
    return client


def add_transaction(db, client, **values):
    invoice_no = values["invoice_no"]
    row = db.query(Transaction).filter(
        Transaction.client_id == client.id,
        Transaction.invoice_no == invoice_no,
        Transaction.source == values["source"],
    ).first()
    if not row:
        db.add(Transaction(org_id=client.org_id, client_id=client.id, **values))


def add_deadline(db, client, filing_type, filing_name, period, due, status="pending", filed_at=None):
    row = db.query(ComplianceDeadline).filter(
        ComplianceDeadline.client_id == client.id,
        ComplianceDeadline.filing_type == filing_type,
        ComplianceDeadline.period == period,
    ).first()
    if not row:
        row = ComplianceDeadline(
            org_id=client.org_id, client_id=client.id, filing_type=filing_type,
            filing_name=filing_name, period=period, deadline=due, status=status,
            filed_at=filed_at, doc_required="gstr2b" if filing_type.startswith("GSTR") else None,
        )
        db.add(row)
        db.flush()
    return row


def seed_peer_pool(db):
    ratios = [
        {"current_ratio": 1.2, "debt_equity_ratio": 1.8, "gross_margin_pct": 22, "asset_turnover": 1.1},
        {"current_ratio": 1.5, "debt_equity_ratio": 1.3, "gross_margin_pct": 26, "asset_turnover": 1.4},
        {"current_ratio": 1.8, "debt_equity_ratio": 0.9, "gross_margin_pct": 31, "asset_turnover": 1.6},
        {"current_ratio": 2.1, "debt_equity_ratio": 0.7, "gross_margin_pct": 34, "asset_turnover": 1.8},
        {"current_ratio": 1.6, "debt_equity_ratio": 1.1, "gross_margin_pct": 29, "asset_turnover": 1.5},
    ]
    now = datetime.now(timezone.utc)
    for index, peer_ratios in enumerate(ratios, start=1):
        name = f"CA Copilot Benchmark Peer {index}"
        org = db.query(Organization).filter(Organization.name == name).first()
        if not org:
            org = Organization(name=name, plan="premium")
            db.add(org)
            db.flush()
        client = get_or_create_client(
            db, org, f"Anonymous Manufacturing Peer {index}",
            industry="Manufacturing", health_score=70 + index,
            benchmark_consent_at=now,
        )
        doc = db.query(Document).filter(
            Document.client_id == client.id, Document.doc_type == "trial_balance"
        ).first()
        if not doc:
            db.add(Document(
                org_id=org.id, client_id=client.id, doc_type="trial_balance",
                s3_key=f"demo/peer-{index}/trial-balance.csv", status="processed",
                ocr_json={"audit_result": {"ratios": peer_ratios}},
            ))


def seed_new_modules(db, org, user, apex, retail, services, today, now):
    period = today.strftime("%Y-%m")
    calendar_rows = [
        (apex, "GSTR3B", today + timedelta(days=1), False, 2, True),
        (apex, "GSTR1", today + timedelta(days=5), False, 1, False),
        (apex, "ROC_AOC4", today + timedelta(days=24), True, 1, True),
        (retail, "GSTR3B", today + timedelta(days=1), False, 4, False),
        (retail, "TDS_26Q", today + timedelta(days=10), True, 2, False),
        (services, "GSTR3B", today + timedelta(days=1), True, 0, False),
        (services, "ROC_AOC4", today + timedelta(days=24), True, 0, False),
    ]
    for client, filing, due, received, late_count, notice in calendar_rows:
        row = db.query(DeadlineClientMap).filter(
            DeadlineClientMap.client_id == client.id,
            DeadlineClientMap.filing_type == filing,
            DeadlineClientMap.period == period,
        ).first()
        if not row:
            row = DeadlineClientMap(
                org_id=org.id, client_id=client.id, filing_type=filing,
                filing_name=FILING_NAMES.get(filing, filing), period=period,
            )
            db.add(row)
        row.deadline = due
        row.data_received = received
        row.data_received_at = now if received else None
        row.data_source = "upload" if received else None
        row.late_count_last_12m = late_count
        row.has_open_notice = notice
        row.risk_score = deadline_risk_score(due, received, late_count, notice, client.health_score, today)

    vendor = db.query(MsmeVendor).filter(
        MsmeVendor.client_id == apex.id, MsmeVendor.vendor_gstin == "27AAACR3333C1Z3"
    ).first()
    if not vendor:
        vendor = MsmeVendor(
            org_id=org.id, client_id=apex.id, vendor_name="Rapid Supplies LLP",
            vendor_gstin="27AAACR3333C1Z3", udyam_reg_no="UDYAM-MH-19-0123456",
            udyam_category="small", registered_at=today - timedelta(days=500),
            verified_at=now,
        )
        db.add(vendor)
        db.flush()
    invoice = db.query(Transaction).filter(
        Transaction.client_id == apex.id, Transaction.invoice_no == "MSME-9001"
    ).first()
    if invoice:
        invoice.date = today - timedelta(days=50)
        violation = db.query(MsmePaymentViolation).filter(
            MsmePaymentViolation.vendor_id == vendor.id,
            MsmePaymentViolation.invoice_id == invoice.id,
        ).first()
        values = msme_violation_values(invoice.date, invoice.amount, today=today)
        if not violation:
            violation = MsmePaymentViolation(
                org_id=org.id, client_id=apex.id, vendor_id=vendor.id,
                invoice_id=invoice.id, invoice_date=invoice.date,
                invoice_amount=invoice.amount, fy=get_fy(invoice.date),
            )
            db.add(violation)
        violation.invoice_date = invoice.date
        violation.invoice_amount = invoice.amount
        violation.fy = get_fy(invoice.date)
        violation.status = "open"
        for key in ("due_date", "days_overdue", "disallowance_amount", "interest_amount"):
            setattr(violation, key, values[key])

    facility = db.query(BankFacility).filter(
        BankFacility.client_id == apex.id, BankFacility.bank_name == "State Bank of India"
    ).first()
    if not facility:
        facility = BankFacility(
            org_id=org.id, client_id=apex.id, bank_name="State Bank of India",
            facility_type="CC", sanctioned_limit=2500000,
            margin_rules={"stock_margin": .25, "debtor_margin": .25, "stock_age_cutoff_days": 180, "debtor_age_cutoff_days": 90, "creditor_deduction": True},
        )
        db.add(facility)
        db.flush()
    if not db.query(InventoryItem).filter(InventoryItem.client_id == apex.id, InventoryItem.period == period).first():
        db.add_all([
            InventoryItem(org_id=org.id, client_id=apex.id, period=period, sku="RM-100", description="Raw material", stock_value=1200000, last_movement_date=today - timedelta(days=12)),
            InventoryItem(org_id=org.id, client_id=apex.id, period=period, sku="FG-OLD", description="Obsolete finished goods", stock_value=250000, last_movement_date=today - timedelta(days=240)),
        ])
    if not db.query(DebtorItem).filter(DebtorItem.client_id == apex.id, DebtorItem.period == period).first():
        db.add_all([
            DebtorItem(org_id=org.id, client_id=apex.id, period=period, debtor_name="Alpha Customer", invoice_date=today - timedelta(days=35), outstanding=700000, payment_history_score=88),
            DebtorItem(org_id=org.id, client_id=apex.id, period=period, debtor_name="Slow Buyer Ltd", invoice_date=today - timedelta(days=105), outstanding=300000, payment_history_score=55),
        ])
    statement = db.query(DrawingPowerStatement).filter(
        DrawingPowerStatement.facility_id == facility.id, DrawingPowerStatement.period == period
    ).first()
    if not statement:
        db.add(DrawingPowerStatement(
            org_id=org.id, client_id=apex.id, facility_id=facility.id, period=period,
            gross_stock=1450000, eligible_stock=1200000, gross_debtors=1000000,
            eligible_debtors=700000, creditors=200000, drawing_power=1225000,
            details={"stock": {"ineligible_value": 250000}, "debtors": {"at_risk_count": 1, "ineligible_value": 300000}},
        ))

    if not db.query(CertificateRecord).filter(CertificateRecord.client_id == apex.id).first():
        cert_fields = {"current_assets": 5200000, "current_liabilities": 2600000, "net_working_capital": 2600000, "current_ratio": 2.0}
        db.add(CertificateRecord(
            org_id=org.id, client_id=apex.id, cert_type="working_capital",
            title=CERTIFICATE_TYPES["working_capital"][0], fields=cert_fields,
            validation={"valid": True, "issues": [], "missing_fields": []},
            status="ready", created_by=user.id,
        ))

    if not db.query(SecretarialDocument).filter(SecretarialDocument.client_id == apex.id).first():
        transcript = "The board approved renewal of the cash credit facility. The directors authorized Ms. Priya Shah to sign all bank documents."
        structured, generated, xml = generate_secretarial_document(
            "board_minutes", apex, transcript,
            {"meeting_type": "Board Meeting", "meeting_date": str(today), "chairman": "Ms. Priya Shah", "directors_present": ["Ms. Priya Shah", "Mr. Karan Mehta"]},
        )
        db.add(SecretarialDocument(
            org_id=org.id, client_id=apex.id, doc_type="board_minutes",
            transcript=transcript, structured_data=structured, generated_text=generated,
            generated_xml=xml, created_by=user.id,
        ))

    if not db.query(LeaseRecord).filter(LeaseRecord.client_id == apex.id).first():
        lease_data = extract_lease_data(
            "Commencement date: 2026-04-01. Lease term: 36 months. Monthly rent: INR 100,000. Security deposit: INR 300,000. IBR: 9%.",
            {"commencement_date": "2026-04-01", "lease_term_months": 36, "base_rent_monthly": 100000, "rent_free_period_months": 2, "incremental_borrowing_rate_pct": 9},
        )
        computed = compute_lease_schedule(lease_data)
        lease_data.update({key: value for key, value in computed.items() if key != "schedule"})
        db.add(LeaseRecord(
            org_id=org.id, client_id=apex.id, name="Mumbai Factory Lease",
            source_text="Demo commercial lease agreement", extracted_data=lease_data,
            schedule=computed["schedule"], ibr_assumed=False, verified=True,
        ))

    credentials = db.query(FirmCredential).filter(FirmCredential.org_id == org.id).first()
    if not credentials:
        credentials = FirmCredential(
            org_id=org.id, firm_name="CA Copilot Demo Firm", icai_regn_no="FRN-012345W",
            founding_year=2008, hq_city="Mumbai", hq_state="Maharashtra",
            partners=[{"name": "Aarav Mehta", "membership_no": "123456", "experience_years": 18, "specializations": ["Statutory Audit", "GST"]}],
            article_clerks=14, total_staff=32, gross_fee_receipts_fy1=15000000,
            gross_fee_receipts_fy2=13500000, gross_fee_receipts_fy3=12000000,
            industries_served=[{"industry": "Manufacturing", "client_count": 18, "years": 12}],
            key_engagements=[{"name": "Manufacturing statutory audit"}, {"name": "PSU internal audit"}],
            peer_review_status="valid", quality_review_date=today - timedelta(days=180),
        )
        db.add(credentials)
        db.flush()
    if not db.query(RfpBid).filter(RfpBid.org_id == org.id).first():
        rfp_text = "The bidder must have at least 10 years of experience, minimum turnover INR 10000000, at least 20 staff, and valid peer review status."
        eligibility = check_rfp_eligibility(rfp_text, credentials)
        db.add(RfpBid(
            org_id=org.id, title="Manufacturing Statutory Audit RFP",
            rfp_text=rfp_text, eligibility=eligibility,
            proposal_text=generate_bid_proposal("Manufacturing Statutory Audit RFP", rfp_text, eligibility, credentials),
            status="generated", created_by=user.id,
        ))

    if not db.query(UserActivityLog).filter(UserActivityLog.org_id == org.id).first():
        db.add_all([
            UserActivityLog(org_id=org.id, user_id=user.id, client_id=apex.id, activity_type="reconciliation_run", duration_seconds=7200),
            UserActivityLog(org_id=org.id, user_id=user.id, client_id=apex.id, activity_type="document_review", duration_seconds=10800),
            UserActivityLog(org_id=org.id, user_id=user.id, client_id=retail.id, activity_type="upload", duration_seconds=3600),
            UserActivityLog(org_id=org.id, user_id=user.id, client_id=retail.id, activity_type="notice_draft", duration_seconds=5400),
            TimesheetEntry(org_id=org.id, user_id=user.id, client_id=apex.id, date=today, hours_logged=4, task_description="GST reconciliation and audit review", billable=True, billing_rate=1800, cost_rate=850),
            TimesheetEntry(org_id=org.id, user_id=user.id, client_id=retail.id, date=today, hours_logged=1.5, task_description="Notice response preparation", billable=True, billing_rate=1800, cost_rate=850),
        ])

    if not db.query(AutopilotSyncRun).filter(AutopilotSyncRun.org_id == org.id).first():
        db.add(AutopilotSyncRun(
            org_id=org.id, client_id=apex.id, source="tally_connector",
            source_name="Apex TallyPrime desktop", period=period,
            status="completed", records_received=128, records_imported=128,
            records_failed=0, completed_at=now, created_by=user.id,
            summary={"threshold_flags": 2, "companies_synced": ["Apex Manufacturing Pvt Ltd"]},
        ))


def main():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == DEMO_EMAIL).first()
        if not user:
            org = db.query(Organization).filter(Organization.name == "CA Copilot Demo Firm").first()
            if not org:
                org = Organization(name="CA Copilot Demo Firm", plan="premium")
                db.add(org)
                db.flush()
            user = User(
                org_id=org.id, email=DEMO_EMAIL,
                password_hash=pwd_ctx.hash(DEMO_PASSWORD), role="partner",
            )
            db.add(user)
            db.flush()
        else:
            org = db.query(Organization).filter(Organization.id == user.org_id).first()
            user.password_hash = pwd_ctx.hash(DEMO_PASSWORD)
        org.plan = "premium"
        now = datetime.now(timezone.utc)
        today = date.today()

        apex = get_or_create_client(
            db, org, "Apex Manufacturing Pvt Ltd",
            gstin="27ABCDE1234F1Z5", email="finance@apex.example.com",
            whatsapp_number="919876543210", whatsapp_consent_at=now,
            benchmark_consent_at=now, industry="Manufacturing", health_score=68,
            entity_type="pvt_ltd", cin="U28999MH2012PTC123456",
            registered_office="Mumbai, Maharashtra",
        )
        retail = get_or_create_client(
            db, org, "Bright Retail LLP", gstin="29AABCT1332L1ZD",
            email="accounts@bright.example.com", industry="Retail", health_score=43,
            entity_type="llp", cin="AAB-1234", registered_office="Bengaluru, Karnataka",
        )
        services = get_or_create_client(
            db, org, "Crest Services Ltd", gstin="07AACCC1234D1Z8",
            email="ops@crest.example.com", industry="Services", health_score=86,
            entity_type="pvt_ltd", cin="U74999DL2015PTC654321",
            registered_office="New Delhi",
        )

        for client in (apex, retail, services):
            seed_client_applicability(db, client)
            if not db.query(ClientHealthHistory).filter(ClientHealthHistory.client_id == client.id).first():
                for days in range(12, 0, -1):
                    score = max(20, min(100, client.health_score - (days % 4) + 2))
                    db.add(ClientHealthHistory(
                        org_id=org.id, client_id=client.id, score=score,
                        tier="green" if score >= 75 else "amber" if score >= 50 else "red",
                        components={"gst": 20, "itc": 18, "notices": 17, "anomaly": 8, "tds": 8},
                        computed_at=now - timedelta(days=days),
                    ))

        current_period = today.strftime("%b %Y")
        add_deadline(db, apex, "GSTR1", "GSTR-1", current_period, today + timedelta(days=5))
        urgent = add_deadline(db, apex, "GSTR3B", "GSTR-3B", current_period, today + timedelta(days=1))
        add_deadline(db, retail, "TDS_26Q", "TDS 26Q", current_period, today + timedelta(days=9))
        add_deadline(db, retail, "GSTR3B", "GSTR-3B", "Previous period", today - timedelta(days=3), "missed")
        add_deadline(db, services, "GSTR1", "GSTR-1", "Previous period", today - timedelta(days=10), "filed", now - timedelta(days=11))

        if not db.query(WhatsAppReminder).filter(WhatsAppReminder.client_id == apex.id).first():
            db.add(WhatsAppReminder(
                org_id=org.id, client_id=apex.id, deadline_id=urgent.id,
                template="data_request_reminder", status="sent", sent_at=now - timedelta(days=1),
            ))

        purchase_rows = [
            ("APX-1001", "Precision Metals Ltd", "27AAACP1111A1Z1", 11800, "exact", 1.0, 0.08, None),
            ("APX-1002", "Nova Components Pvt Ltd", "27AAACN2222B1Z2", 23600, "tolerance", 0.9, 0.18, None),
            ("APX-1003", "Rapid Supplies LLP", "27AAACR3333C1Z3", 49999, "unmatched", None, 0.82, "Non-standard tax rate: 16.7%"),
            ("APX-1004", "Precision Metals Ltd", "27AAACP1111A1Z1", 50000, "unmatched", None, 0.91, "Duplicate invoice"),
        ]
        for index, (invoice, vendor, gstin, amount, match, confidence, risk, fraud) in enumerate(purchase_rows):
            add_transaction(
                db, apex, source="upload", invoice_no=invoice, vendor_name=vendor,
                vendor_gstin=gstin, amount=amount, tax_amount=amount * 0.18,
                date=today - timedelta(days=index + 1), match_status=match,
                match_confidence=confidence, anomaly_score=risk, fraud_flag=fraud,
                fingerprint=f"demo-{invoice}-upload",
            )
        for invoice, vendor, gstin, amount in [
            ("APX-1001", "Precision Metals", "27AAACP1111A1Z1", 11800),
            ("APX-1002", "Nova Components", "27AAACN2222B1Z2", 23602),
        ]:
            add_transaction(
                db, apex, source="gstr2b", invoice_no=invoice, vendor_name=vendor,
                vendor_gstin=gstin, amount=amount, date=today - timedelta(days=2),
                match_status="unmatched", fingerprint=f"demo-{invoice}-gstr2b",
            )

        add_transaction(
            db, apex, source="upload", invoice_no="MSME-9001",
            vendor_name="Rapid Supplies LLP", vendor_gstin="27AAACR3333C1Z3",
            amount=185000, tax_amount=33300, date=today - timedelta(days=50),
            match_status="unmatched", anomaly_score=0.42,
            fingerprint="demo-MSME-9001-upload",
        )

        db.flush()
        if not db.query(AnomalyFlag).filter(AnomalyFlag.client_id == apex.id).first():
            transaction = db.query(Transaction).filter(
                Transaction.client_id == apex.id, Transaction.invoice_no == "APX-1004"
            ).first()
            db.add_all([
                AnomalyFlag(org_id=org.id, client_id=apex.id, transaction_id=transaction.id, flag_type="isolation_forest", risk_score=0.91, details={"reason": "Amount deviates sharply from vendor baseline"}),
                AnomalyFlag(org_id=org.id, client_id=apex.id, transaction_id=transaction.id, flag_type="threshold_gaming", risk_score=0.75, details={"amount": 50000}),
            ])

        if not db.query(ReconciliationResult).filter(ReconciliationResult.client_id == apex.id).first():
            db.add(ReconciliationResult(
                org_id=org.id, client_id=apex.id, period=current_period,
                total_purchase=115399, total_gstr2b=35402, matched_count=2,
                unmatched_count=2, mismatch_value=79999,
            ))

        if not db.query(Document).filter(Document.client_id == apex.id).first():
            db.add_all([
                Document(org_id=org.id, client_id=apex.id, doc_type="purchase_register", s3_key="demo/apex/purchase.csv", status="processed"),
                Document(org_id=org.id, client_id=apex.id, doc_type="gstr2b", s3_key="demo/apex/gstr2b.json", status="processed"),
                Document(org_id=org.id, client_id=apex.id, doc_type="notice", s3_key="demo/apex/notice.pdf", status="ocr_complete", ocr_text="Show Cause Notice under Section 73 for A.Y. 2025-26"),
            ])

        trial_balance = db.query(Document).filter(
            Document.client_id == apex.id, Document.doc_type == "trial_balance"
        ).first()
        if not trial_balance:
            db.add(Document(
                org_id=org.id, client_id=apex.id, doc_type="trial_balance",
                s3_key="demo/apex/trial-balance.csv", status="processed",
                ocr_json={"audit_result": {"ratios": DEMO_RATIOS}},
            ))
        else:
            trial_balance.ocr_json = {"audit_result": {"ratios": DEMO_RATIOS}}

        seed_new_modules(db, org, user, apex, retail, services, today, now)
        seed_peer_pool(db)
        refresh_autopilot_exceptions(db, str(org.id))
        db.commit()
        print("Demo data ready for demo@cacopilot.in")
    finally:
        db.close()


if __name__ == "__main__":
    main()
