"""Seed and exercise a 2,000-company synthetic tenant.

Run inside the backend container:
    python scripts/stress_2000_companies.py --companies 2000
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from passlib.context import CryptContext

from app.database import SessionLocal, engine
from app.main import app
from app.models.anomaly_flag import AnomalyFlag
from app.models.autopilot import AutopilotException, AutopilotSyncRun
from app.models.client import Client
from app.models.compliance_deadline import ComplianceDeadline
from app.models.document import Document
from app.models.extensions import (
    BankFacility,
    CertificateRecord,
    DeadlineClientMap,
    DebtorItem,
    FirmCredential,
    InventoryItem,
    LeaseRecord,
    MsmePaymentViolation,
    MsmeVendor,
    RfpBid,
    SecretarialDocument,
    TimesheetEntry,
)
from app.models.health_history import ClientHealthHistory
from app.models.organization import Organization
from app.models.practice_ops import (
    AttendanceEntry,
    BillingPlan,
    ClientPortalContact,
    CredentialVaultItem,
    DaybookEntry,
    ImportJob,
    PortalRequest,
    PracticeInvoice,
    PracticeTask,
    SavedView,
)
from app.models.reconciliation import ReconciliationConfig, ReconciliationResult
from app.models.saved_query import SavedQuery
from app.models.transaction import Transaction
from app.models.user import User
from app.models.whatsapp_reminder import WhatsAppReminder
from app.utils.jwt_utils import create_access_token


logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("ca_platform").setLevel(logging.WARNING)
engine.echo = False

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
REPORT_DIR = Path("stress_reports")


def as_json(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


class StressRun:
    def __init__(self, companies: int, seed: int):
        self.companies = companies
        self.random = random.Random(seed)
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        self.client = TestClient(app, raise_server_exceptions=False)
        self.failures: list[dict] = []
        self.gaps: list[dict] = []
        self.timings: list[dict] = []
        self.created: dict[str, int] = {}
        self.ids: dict[str, str] = {}

    def record_failure(self, feature: str, detail: str, response=None, error: Exception | None = None):
        entry = {"feature": feature, "detail": detail}
        if response is not None:
            entry["status_code"] = response.status_code
            try:
                entry["response"] = response.json()
            except Exception:
                entry["response"] = response.text[:500]
        if error is not None:
            entry["error"] = repr(error)
        self.failures.append(entry)

    def record_gap(self, feature: str, detail: str, observed=None):
        self.gaps.append({"feature": feature, "detail": detail, "observed": observed})

    def timed(self, feature: str, fn: Callable):
        start = time.perf_counter()
        try:
            return fn()
        finally:
            self.timings.append({"feature": feature, "seconds": round(time.perf_counter() - start, 3)})

    def expect(self, feature: str, method: str, path: str, ok=(200,), **kwargs):
        response = getattr(self.client, method)(path, **kwargs)
        if response.status_code not in ok:
            self.record_failure(feature, f"{method.upper()} {path} expected {ok}", response=response)
            return None
        try:
            return response.json()
        except Exception:
            return response.text

    def setup_tenant(self):
        db = SessionLocal()
        try:
            org = Organization(
                name=f"Stress CA Firm {self.run_id}",
                plan="premium",
                gstin="27ABCDE1234F1Z5",
            )
            db.add(org)
            db.flush()
            user = User(
                org_id=org.id,
                email=f"stress-{self.run_id}@example.com",
                password_hash=pwd_ctx.hash("StressPass123"),
                role="partner",
                last_active_at=datetime.now(timezone.utc),
            )
            manager = User(
                org_id=org.id,
                email=f"stress-manager-{self.run_id}@example.com",
                password_hash=pwd_ctx.hash("StressPass123"),
                role="manager",
            )
            article = User(
                org_id=org.id,
                email=f"stress-article-{self.run_id}@example.com",
                password_hash=pwd_ctx.hash("StressPass123"),
                role="article",
            )
            db.add_all([user, manager, article])
            db.commit()
            token_data = {"sub": str(user.id), "org_id": str(org.id), "role": user.role, "email": user.email}
            self.client.headers.update({"Authorization": f"Bearer {create_access_token(token_data)}"})
            self.ids.update({
                "org": str(org.id),
                "user": str(user.id),
                "manager": str(manager.id),
                "article": str(article.id),
                "user_email": user.email,
            })
        finally:
            db.close()

    def seed(self):
        db = SessionLocal()
        today = date.today()
        industries = ["manufacturing", "retail", "services", "construction", "technology"]
        entity_types = ["pvt_ltd", "llp", "partnership", "proprietorship", "trust"]
        try:
            org_id = self.ids["org"]
            user_id = self.ids["user"]
            clients = []
            for i in range(self.companies):
                clients.append(Client(
                    org_id=org_id,
                    name=f"Synthetic Company {i + 1:04d} Pvt Ltd",
                    gstin=f"{27 + i % 9:02d}ABCDE{i % 10000:04d}F1Z{(i % 9) + 1}",
                    email=f"client{i + 1:04d}@example.com",
                    whatsapp_number=f"9198{i:08d}"[:12],
                    whatsapp_consent_at=datetime.now(timezone.utc) if i % 3 == 0 else None,
                    health_score=(i * 37) % 101,
                    industry=industries[i % len(industries)],
                    entity_type=entity_types[i % len(entity_types)],
                    cin=f"U{i % 100000:05d}MH2024PTC{i % 1000000:06d}",
                    registered_office=f"{i + 1} Compliance Street, Mumbai",
                    benchmark_consent_at=datetime.now(timezone.utc) if i % 2 == 0 else None,
                ))
            db.add_all(clients)
            db.flush()

            docs = []
            txns = []
            deadlines = []
            calendar = []
            health = []
            anomalies = []
            autopilot_exceptions = []
            autopilot_sync_runs = []
            recon_results = []
            recon_cfg = []
            tasks = []
            daybook = []
            plans = []
            invoices = []
            portal_contacts = []
            portal_requests = []
            attendance = []
            vault = []
            import_jobs = []
            saved_views = []
            vendors = []
            facilities = []
            certs = []
            secretarial = []
            leases = []
            timesheets = []
            reminders = []

            for i, client in enumerate(clients):
                period = today.strftime("%Y-%m")
                deadline_day = today + timedelta(days=(i % 45) - 10)
                docs.append(Document(
                    org_id=org_id, client_id=client.id, doc_type="trial_balance",
                    s3_key=f"{org_id}/{client.id}/trial-balance-{i}.xlsx",
                    status="processed", ocr_json={"audit_result": {"ratios": {
                        "current_ratio": round(0.8 + (i % 20) / 10, 2),
                        "debt_equity_ratio": round(0.2 + (i % 15) / 10, 2),
                        "gross_margin_pct": round(8 + (i % 35), 2),
                        "asset_turnover": round(0.5 + (i % 10) / 10, 2),
                    }}},
                ))
                docs.append(Document(
                    org_id=org_id, client_id=client.id, doc_type="notice",
                    s3_key=f"{org_id}/{client.id}/notice-{i}.pdf", status="ocr_complete",
                    ocr_json={"draft_result": {"summary": "Synthetic notice"}},
                ))
                for j in range(2):
                    amount = Decimal("49500.00") if j == 0 and i % 7 == 0 else Decimal(str(1000 + ((i * 97 + j * 313) % 200000)))
                    txns.append(Transaction(
                        org_id=org_id, client_id=client.id, invoice_no=f"INV-{i:04d}-{j}",
                        vendor_gstin=f"27VENDR{i % 10000:04d}F1Z{j + 1}",
                        vendor_name=f"Vendor {i % 300:03d}", amount=amount,
                        tax_amount=round(amount * Decimal("0.18"), 2),
                        date=today - timedelta(days=(i + j) % 120),
                        match_status=["unmatched", "exact", "tolerance", "fuzzy"][(i + j) % 4],
                        match_confidence=Decimal(str(70 + (i % 30))),
                        anomaly_score=Decimal("0.91") if i % 13 == 0 else None,
                        fraud_flag="Potential threshold gaming" if amount == Decimal("49500.00") else None,
                        source="upload",
                    ))
                deadlines.append(ComplianceDeadline(
                    org_id=org_id, client_id=client.id, filing_type="GSTR3B",
                    filing_name="GSTR-3B", period=period, deadline=deadline_day,
                    status=["pending", "filed", "missed"][i % 3], doc_required="gstr2b",
                ))
                calendar.append(DeadlineClientMap(
                    org_id=org_id, client_id=client.id, filing_type="GSTR3B",
                    filing_name="GSTR-3B", period=period, deadline=deadline_day,
                    data_received=i % 4 == 0, status="pending", late_count_last_12m=i % 5,
                    has_open_notice=i % 11 == 0, risk_score=Decimal(str((i % 10) + 0.5)),
                ))
                health.append(ClientHealthHistory(
                    org_id=org_id, client_id=client.id, score=client.health_score,
                    tier="green" if client.health_score >= 75 else "amber" if client.health_score >= 50 else "red",
                    components={"synthetic": True},
                ))
                recon_results.append(ReconciliationResult(
                    org_id=org_id, client_id=client.id, period=period,
                    total_purchase=Decimal("200000.00"), total_gstr2b=Decimal("190000.00"),
                    matched_count=4, unmatched_count=i % 6, mismatch_value=Decimal(str((i % 6) * 10000)),
                ))
                autopilot_sync_runs.append(AutopilotSyncRun(
                    org_id=org_id, client_id=client.id, source="tally_connector",
                    source_name="Synthetic Tally", period=period, status="completed",
                    records_received=2, records_imported=2, records_failed=0,
                    summary={"synthetic": True}, completed_at=datetime.now(timezone.utc),
                    created_by=user_id,
                ))
                autopilot_exceptions.append(AutopilotException(
                    org_id=org_id, client_id=client.id,
                    fingerprint=f"stress-autopilot-{self.run_id}-{i}",
                    source_type="deadline", title=f"Synthetic exception {i}",
                    description="Synthetic client exception for 2,000-company coverage.",
                    severity=["low", "medium", "high", "critical"][i % 4],
                    impact_amount=Decimal(str((i % 10) * 10000)),
                    due_date=deadline_day, status="open",
                    evidence={"synthetic": True},
                    recommended_actions=[{"label": "Review", "action_type": "review_note"}],
                ))
                recon_cfg.append(ReconciliationConfig(client_id=client.id, amount_tolerance=5, date_tolerance=3, fuzzy_threshold=85))
                tasks.append(PracticeTask(
                    org_id=org_id, client_id=client.id, title=f"Monthly compliance review {i}",
                    priority=["low", "medium", "high"][i % 3], status=["open", "in_progress", "review", "done"][i % 4],
                    stage=["maker", "checker", "review"][i % 3], due_date=deadline_day, assigned_to=user_id, created_by=user_id,
                ))
                daybook.append(DaybookEntry(org_id=org_id, client_id=client.id, entry_date=today, summary=f"Followed up with company {i}", created_by=user_id))
                plans.append(BillingPlan(org_id=org_id, client_id=client.id, name="Monthly retainer", amount=Decimal("15000.00"), tax_rate=Decimal("18.00")))
                invoices.append(PracticeInvoice(
                    org_id=org_id, client_id=client.id, invoice_no=f"STR-{self.run_id}-{i:04d}",
                    issue_date=today - timedelta(days=30), due_date=today - timedelta(days=i % 20),
                    line_items=[{"description": "Compliance retainer", "amount": 15000}], subtotal=Decimal("15000.00"),
                    tax=Decimal("2700.00"), total=Decimal("17700.00"), amount_paid=Decimal(str((i % 3) * 5000)),
                    status=["sent", "part_paid", "paid"][i % 3], created_by=user_id,
                ))
                portal_contacts.append(ClientPortalContact(org_id=org_id, client_id=client.id, name=f"Client Contact {i}", email=f"contact{i}@example.com"))
                portal_requests.append(PortalRequest(org_id=org_id, client_id=client.id, title=f"Upload GST data {i}", due_date=deadline_day, created_by=user_id))
                vault.append(CredentialVaultItem(org_id=org_id, client_id=client.id, label=f"GST portal {i}", username=f"user{i}", masked_secret="****1234", expires_on=today + timedelta(days=i % 60), created_by=user_id))
                import_jobs.append(ImportJob(org_id=org_id, client_id=client.id, import_type="tally_vouchers", source_name=f"sample-{i}.xlsx", status="validated", mapping={"date": "date"}, records_total=2, records_valid=2, created_by=user_id))
                vendors.append(MsmeVendor(org_id=org_id, client_id=client.id, vendor_name=f"MSME Vendor {i}", vendor_gstin=f"27MSMEV{i % 10000:04d}F1Z5", udyam_category=["micro", "small", "medium"][i % 3], verified_at=datetime.now(timezone.utc)))
                facilities.append(BankFacility(org_id=org_id, client_id=client.id, bank_name=f"Bank {i % 20}", sanctioned_limit=Decimal("1000000.00"), margin_rules={"stock_margin": 0.25, "debtor_margin": 0.25}))
                certs.append(CertificateRecord(org_id=org_id, client_id=client.id, cert_type="turnover", title="Certificate of Turnover", fields={"turnover_fy1": 1000000, "turnover_fy2": 1100000, "turnover_fy3": 1200000, "export_turnover": 0}, validation={"valid": True, "issues": [], "missing_fields": []}, status="ready", created_by=user_id))
                secretarial.append(SecretarialDocument(org_id=org_id, client_id=client.id, doc_type="board_minutes", structured_data={"meeting_date": str(today)}, generated_text="Synthetic board minutes", created_by=user_id))
                leases.append(LeaseRecord(org_id=org_id, client_id=client.id, name=f"Office lease {i}", extracted_data={"initial_lease_liability": 100000}, schedule=[{"month": 1, "payment": 10000, "interest_expense": 800, "principal": 9200, "lease_liability": 90800, "rou_asset": 100000}]))
                timesheets.append(TimesheetEntry(org_id=org_id, user_id=user_id, client_id=client.id, date=today, hours_logged=Decimal("1.50"), task_description="Synthetic work", billing_rate=Decimal("1500.00"), cost_rate=Decimal("800.00")))
                if i < 30:
                    attendance.append(AttendanceEntry(org_id=org_id, user_id=[user_id, self.ids["manager"], self.ids["article"]][i % 3], work_date=today - timedelta(days=i // 3), hours_available=8, hours_booked=i % 8))
                if i % 4 == 0:
                    saved_views.append(SavedView(org_id=org_id, user_id=user_id, name=f"Stress view {i}", view_type="report", filters={"industry": client.industry}, columns=["client", "status"], is_shared=i % 8 == 0))

            db.add_all(docs + txns)
            db.flush()
            db.add_all(vendors)
            db.flush()
            for i, client in enumerate(clients):
                txn = txns[i * 2]
                anomalies.append(AnomalyFlag(org_id=org_id, client_id=client.id, transaction_id=txn.id, flag_type="threshold_gaming", risk_score=Decimal("0.91"), details={"amount": float(txn.amount or 0)}, reviewed=False))
            for i, vendor in enumerate(vendors):
                txn = txns[i * 2]
                violations = MsmePaymentViolation(
                    org_id=org_id, client_id=vendor.client_id, vendor_id=vendor.id, invoice_id=txn.id,
                    invoice_date=today - timedelta(days=90), invoice_amount=Decimal("65000.00"),
                    due_date=today - timedelta(days=45), days_overdue=45,
                    disallowance_amount=Decimal("65000.00"), interest_amount=Decimal("360.62"),
                    fy="2025-26", status="open",
                )
                db.add(violations)
            db.add_all(deadlines + calendar + health + anomalies + recon_results + recon_cfg)
            db.add_all(autopilot_exceptions + autopilot_sync_runs)
            db.add_all(tasks + daybook + plans + invoices + portal_contacts + portal_requests + attendance + vault + import_jobs + saved_views)
            db.add_all(facilities + certs + secretarial + leases + timesheets)
            db.add(FirmCredential(org_id=org_id, firm_name="Stress CA LLP", founding_year=2010, total_staff=75, article_clerks=20, industries_served=[{"name": "manufacturing"}]))
            db.add(RfpBid(org_id=org_id, title="Synthetic RFP", rfp_text="Need audit firm with 10 years experience", eligibility={"eligible": True}, proposal_text="Synthetic proposal", status="generated", created_by=user_id))
            db.add(SavedQuery(org_id=org_id, user_id=user_id, name="High risk clients", nl_query="Which clients have health score below 50?"))
            for dl in deadlines:
                reminders.append(WhatsAppReminder(org_id=org_id, client_id=dl.client_id, deadline_id=dl.id, template="data_request_reminder", status="sent"))
            db.add_all(reminders)
            db.commit()
            self.ids["client"] = str(clients[0].id)
            self.ids["client_2"] = str(clients[1].id) if len(clients) > 1 else str(clients[0].id)
            self.ids["client_gstin"] = clients[0].gstin
            self.ids["document"] = str(docs[0].id)
            self.ids["transaction"] = str(txns[0].id)
            self.ids["reconciliation_result"] = str(recon_results[0].id)
            self.created = {
                "clients": len(clients), "documents": len(docs), "transactions": len(txns),
                "deadlines": len(deadlines), "calendar_items": len(calendar),
                "practice_tasks": len(tasks), "invoices": len(invoices),
                "portal_requests": len(portal_requests), "msme_vendors": len(vendors),
                "msme_violations": len(vendors), "certificates": len(certs),
                "secretarial_documents": len(secretarial), "leases": len(leases),
                "timesheets": len(timesheets), "anomaly_flags": len(anomalies),
                "autopilot_exceptions": len(autopilot_exceptions),
                "autopilot_sync_runs": len(autopilot_sync_runs),
                "whatsapp_reminders": len(reminders), "billing_plans": len(plans),
                "portal_contacts": len(portal_contacts), "vault_items": len(vault),
                "import_jobs": len(import_jobs),
            }
        finally:
            db.close()

    def run_auth_org_tests(self):
        register_email = f"phase1-{self.run_id}@example.com"
        registered = self.expect("auth-register", "post", "/auth/register", ok=(201,), json={
            "org_name": "Phase 1 Synthetic Firm",
            "email": register_email,
            "password": "PhaseOnePass123",
        })
        if not isinstance(registered, dict) or not registered.get("access_token") or not registered.get("refresh_token"):
            self.record_gap("auth-register", "Register did not return both access and refresh tokens", registered)
            return

        original_auth = self.client.headers.get("Authorization")
        self.client.headers.update({"Authorization": f"Bearer {registered['access_token']}"})
        self.expect("organization-profile", "get", "/organizations/me")
        self.expect("organization-update", "patch", "/organizations/me", json={
            "name": "Phase 1 Synthetic Firm Updated",
            "gstin": "27ABCDE1234F1Z5",
        })

        invalid_org = self.client.patch("/organizations/me", json={"gstin": "bad-gstin"})
        if invalid_org.status_code != 422:
            self.record_failure("organization-validation", "Invalid GSTIN should be rejected", response=invalid_org)

        refreshed = self.expect("auth-refresh", "post", "/auth/refresh", json={"refresh_token": registered["refresh_token"]})
        old_refresh = self.client.post("/auth/refresh", json={"refresh_token": registered["refresh_token"]})
        if old_refresh.status_code != 401:
            self.record_failure("auth-refresh-rotation", "Old refresh token should be revoked after rotation", response=old_refresh)

        if not isinstance(refreshed, dict) or not refreshed.get("access_token") or not refreshed.get("refresh_token"):
            self.record_gap("auth-refresh", "Refresh did not return rotated tokens", refreshed)
            if original_auth:
                self.client.headers.update({"Authorization": original_auth})
            return

        self.client.headers.update({"Authorization": f"Bearer {refreshed['access_token']}"})
        self.expect("auth-refreshed-access", "get", "/organizations/me")
        self.expect("auth-logout", "post", "/auth/logout", json={})

        revoked_access = self.client.get("/organizations/me")
        if revoked_access.status_code != 401:
            self.record_failure("auth-logout-access-revocation", "Access token should be rejected after logout", response=revoked_access)

        revoked_refresh = self.client.post("/auth/refresh", json={"refresh_token": refreshed["refresh_token"]})
        if revoked_refresh.status_code != 401:
            self.record_failure("auth-logout-refresh-revocation", "Refresh token should be rejected after logout", response=revoked_refresh)

        relogin = self.expect("auth-login", "post", "/auth/login", json={
            "email": self.ids["user_email"],
            "password": "StressPass123",
        })
        if isinstance(relogin, dict) and relogin.get("access_token"):
            self.client.headers.update({"Authorization": f"Bearer {relogin['access_token']}"})
        elif original_auth:
            self.client.headers.update({"Authorization": original_auth})
            self.record_failure("auth-login", "Could not restore stress tenant auth after logout flow")

    def run_feature_tests(self):
        today = date.today()
        cid = self.ids["client"]
        txid = self.ids["transaction"]
        docid = self.ids["document"]
        recon_result_id = self.ids["reconciliation_result"]
        endpoints = [
            ("auth", "get", "/organizations/me"),
            ("users", "get", "/users"),
            ("clients", "get", "/clients"),
            ("clients", "get", f"/clients/{cid}"),
            ("clients", "get", f"/clients/{cid}/summary"),
            ("documents", "get", "/documents?limit=50"),
            ("reconciliation", "get", f"/reconciliation/transactions?client_id={cid}&limit=100"),
            ("reconciliation", "get", f"/reconciliation/results/{cid}"),
            ("deadlines", "get", "/deadlines"),
            ("deadlines", "get", f"/deadlines/client/{cid}"),
            ("health", "get", "/health-scores"),
            ("anomalies", "get", "/anomalies"),
            ("invoices", "get", "/invoices/fraud-queue"),
            ("notices", "get", "/notices"),
            ("benchmarking", "get", f"/benchmarking/{cid}"),
            ("query", "get", "/query/starters"),
            ("query", "get", "/query/saved"),
            ("whatsapp", "get", "/whatsapp/status"),
            ("autopilot", "get", "/autopilot/overview?auto_refresh=false"),
            ("autopilot", "get", "/autopilot/exceptions?status="),
            ("autopilot", "get", "/autopilot/sync-runs"),
            ("work", "get", "/work/overview"),
            ("work", "get", "/work/tasks"),
            ("work", "get", "/work/daybook"),
            ("billing", "get", "/billing/overview"),
            ("billing", "get", "/billing/plans"),
            ("billing", "get", "/billing/invoices"),
            ("portal", "get", "/portal/contacts"),
            ("portal", "get", "/portal/requests"),
            ("portal", "get", f"/portal/client/{cid}/snapshot"),
            ("team", "get", "/team/overview"),
            ("team", "get", "/team/attendance"),
            ("vault", "get", "/vault/items"),
            ("imports", "get", "/imports/jobs"),
            ("reports", "get", "/reports/overview"),
            ("reports", "get", "/reports/saved-views"),
            ("calendar", "get", "/calendar/overview"),
            ("calendar", "get", f"/calendar/GSTR3B/{today.strftime('%Y-%m')}/clients"),
            ("msme", "get", "/msme/vendors"),
            ("msme", "get", "/msme/violations"),
            ("drawing-power", "get", "/drawing-power/facilities"),
            ("drawing-power", "get", "/drawing-power/statements"),
            ("certificates", "get", "/certificates/types"),
            ("certificates", "get", "/certificates"),
            ("secretarial", "get", "/secretarial"),
            ("leases", "get", "/leases"),
            ("rfp", "get", "/rfp/credentials"),
            ("rfp", "get", "/rfp/bids"),
            ("timesheets", "get", f"/timesheets/entries?month={today.strftime('%Y-%m')}"),
            ("timesheets", "get", f"/timesheets/profitability?month={today.strftime('%Y-%m')}"),
        ]
        for feature, method, path in endpoints:
            result = self.timed(f"{method.upper()} {path}", lambda m=method, p=path, f=feature: self.expect(f, m, p))
            if path in {"/billing/invoices"} and isinstance(result, list) and len(result) < self.companies:
                self.record_gap(feature, "List endpoint did not expose close to the 2,000 seeded companies; pagination/export/filtering is needed for full-practice scale.", {"path": path, "rows": len(result)})

        client_search = self.expect("clients-search", "get", "/clients?search=Synthetic%20Company%200001&limit=10")
        if isinstance(client_search, list) and not any(row.get("id") == cid for row in client_search):
            self.record_failure("clients-search", "Search should find the known seeded client")

        health_history = self.expect("client-health-history", "get", f"/clients/{cid}/health-history")
        if isinstance(health_history, list) and len(health_history) == 0:
            self.record_gap("client-health-history", "Seeded client health history was not returned")

        doc_detail = self.expect("document-detail", "get", f"/documents/{docid}")
        if isinstance(doc_detail, dict) and doc_detail.get("client_id") != cid:
            self.record_failure("document-detail", "Document detail returned the wrong client")
        filtered_docs = self.expect("documents-filter", "get", f"/documents?client_id={cid}&doc_type=trial_balance&status=processed&limit=10")
        if isinstance(filtered_docs, list) and not any(row.get("id") == docid for row in filtered_docs):
            self.record_failure("documents-filter", "Filtered document list should include the known processed trial balance")
        process_processed = self.client.post(f"/documents/{docid}/process")
        if process_processed.status_code != 409:
            self.record_failure("documents-process-state", "Already processed documents should not be re-queued", response=process_processed)
        retry_processed = self.client.post(f"/documents/{docid}/retry-ocr")
        if retry_processed.status_code != 409:
            self.record_failure("documents-retry-state", "Only failed documents should be accepted for OCR retry", response=retry_processed)

        recon_config = self.expect("reconciliation-config-get", "get", f"/reconciliation/config/{cid}")
        if isinstance(recon_config, dict) and recon_config.get("client_id") != cid:
            self.record_failure("reconciliation-config-get", "Config endpoint returned wrong client")
        unmatched_txns = self.expect("reconciliation-transaction-filter", "get", f"/reconciliation/transactions?client_id={cid}&match_status=unmatched&limit=20")
        if isinstance(unmatched_txns, list) and not all(row.get("match_status") == "unmatched" for row in unmatched_txns):
            self.record_failure("reconciliation-transaction-filter", "match_status filter returned mixed statuses")
        export_response = self.client.get(f"/reconciliation/export/{recon_result_id}")
        if export_response.status_code != 200:
            self.record_failure("reconciliation-export", "Seeded reconciliation result should export", response=export_response)
        elif "spreadsheet" not in export_response.headers.get("content-type", ""):
            self.record_failure("reconciliation-export", "Export should return spreadsheet content")

        post_cases = [
            ("clients-create", "post", "/clients", {"name": "API Edge Client", "email": "api-edge@example.com", "entity_type": "pvt_ltd"}, (201,)),
            ("recon-config", "put", f"/reconciliation/config/{cid}", {"amount_tolerance": 7, "date_tolerance": 5, "fuzzy_threshold": 82}, (200,)),
            ("reconciliation-run", "post", "/reconciliation/run", {"client_id": cid, "period": today.strftime("%Y-%m")}, (200,)),
            ("deadline-create", "post", "/deadlines", {"client_id": cid, "filing_type": "ADV_TAX", "filing_name": "Advance Tax", "period": today.strftime("%Y-%m"), "deadline": str(today + timedelta(days=15)), "doc_required": "bank_statement"}, (201,)),
            ("work-task-create", "post", "/work/tasks", {"client_id": cid, "title": "API stress task", "due_date": str(today)}, (201,)),
            ("billing-plan-create", "post", "/billing/plans", {"client_id": cid, "name": "API plan", "amount": 25000}, (201,)),
            ("billing-invoice-create", "post", "/billing/invoices", {"client_id": cid, "invoice_no": f"API-{self.run_id}", "line_items": [{"description": "Stress", "amount": 1000}]}, (201,)),
            ("portal-contact-create", "post", "/portal/contacts", {"client_id": cid, "name": "API Contact", "email": f"api-contact-{self.run_id}@example.com"}, (201,)),
            ("portal-request-create", "post", "/portal/requests", {"client_id": cid, "title": "API document request"}, (201,)),
            ("attendance-upsert", "post", "/team/attendance", {"work_date": str(today), "hours_available": 8, "hours_booked": 4}, (201,)),
            ("vault-create", "post", "/vault/items", {"client_id": cid, "label": "API Vault", "secret_hint": "secret1234"}, (201,)),
            ("import-create", "post", "/imports/jobs", {"client_id": cid, "source_name": "api.csv", "sample_rows": [{"date": str(today), "voucher_no": "V1", "party_name": "P", "amount": "100"}]}, (201,)),
            ("saved-view-create", "post", "/reports/saved-views", {"name": "API saved view", "columns": ["client"]}, (201,)),
            ("msme-vendor-create", "post", "/msme/vendors", {"client_id": cid, "vendor_name": "API MSME", "vendor_gstin": f"27APIXX{self.run_id[-4:]}F1Z5", "udyam_category": "micro"}, (201,)),
            ("dp-facility-create", "post", "/drawing-power/facilities", {"client_id": cid, "bank_name": "API Bank", "sanctioned_limit": 500000}, (201,)),
            ("certificate-create", "post", "/certificates", {"client_id": cid, "cert_type": "turnover", "fields": {"turnover_fy1": 1, "turnover_fy2": 2, "turnover_fy3": 3, "export_turnover": 0}}, (201,)),
            ("secretarial-create", "post", "/secretarial", {"client_id": cid, "doc_type": "board_minutes", "transcript": "Approved opening bank account."}, (201,)),
            ("lease-create", "post", "/leases", {"client_id": cid, "name": "API lease", "data": {"monthly_payment": 10000, "lease_term_months": 12}}, (201,)),
            ("timesheet-create", "post", "/timesheets/entries", {"client_id": cid, "date": str(today), "hours_logged": 1, "task_description": "API stress"}, (201,)),
            ("autopilot-followup", "post", "/autopilot/followups", {"client_id": cid, "message": "Synthetic follow-up"}, (201,)),
            ("whatsapp-consent-link", "post", f"/whatsapp/consent-link/{cid}", {}, (200,)),
        ]
        created_invoice_id = None
        created_facility_id = None
        for feature, method, path, payload, ok in post_cases:
            result = self.timed(f"{method.upper()} {path}", lambda m=method, p=path, f=feature, body=payload, expected=ok: self.expect(f, m, p, ok=expected, json=body))
            if feature == "clients-create" and isinstance(result, dict):
                self.ids["api_client"] = result.get("id")
            if feature == "billing-invoice-create" and isinstance(result, dict):
                created_invoice_id = result.get("id")
            if feature == "dp-facility-create" and isinstance(result, dict):
                created_facility_id = result.get("id")

        api_client_id = self.ids.get("api_client")
        if api_client_id:
            updated_client = self.expect("clients-update", "patch", f"/clients/{api_client_id}", json={
                "name": "API Edge Client Updated",
                "gstin": f"27APICL{self.run_id[-4:]}F1Z5",
                "whatsapp_number": "+919876543210",
                "entity_type": "llp",
            })
            if isinstance(updated_client, dict) and updated_client.get("entity_type") != "llp":
                self.record_failure("clients-update", "Client update did not persist normalized entity type")

            delete_response = self.client.delete(f"/clients/{api_client_id}")
            if delete_response.status_code != 204:
                self.record_failure("clients-delete", "Partner should be able to delete client", response=delete_response)
            after_delete = self.client.get(f"/clients/{api_client_id}")
            if after_delete.status_code != 404:
                self.record_failure("clients-delete-confirm", "Deleted client should not be retrievable", response=after_delete)

        if created_invoice_id:
            self.expect("billing-payment", "post", f"/billing/invoices/{created_invoice_id}/payments", ok=(201,), json={"amount": 1180, "paid_at": str(today)})
        if created_facility_id:
            self.expect("drawing-power-ledger", "post", "/drawing-power/ledger", json={
                "client_id": cid, "period": today.strftime("%Y-%m"),
                "inventory": [{"sku": "API-SKU", "stock_value": 100000, "last_movement_date": str(today)}],
                "debtors": [{"debtor_name": "API Debtor", "invoice_date": str(today - timedelta(days=10)), "outstanding": 50000}],
            })
            self.expect("drawing-power-compute", "post", "/drawing-power/compute", json={"facility_id": created_facility_id, "period": today.strftime("%Y-%m"), "creditors": 10000})

        self.expect("invoice-clear-flag", "patch", f"/invoices/{txid}/clear-flag", json={})

        negative_cases = [
            ("validation-client-email", "post", "/clients", {"name": "Bad Email", "email": "not-an-email"}, (422,)),
            ("validation-client-gstin", "post", "/clients", {"name": "Bad GSTIN", "gstin": "27BAD"}, (422,)),
            ("duplicate-client-gstin", "post", "/clients", {"name": "Duplicate GSTIN", "gstin": self.ids["client_gstin"]}, (400,)),
            ("validation-recon-config", "put", f"/reconciliation/config/{cid}", {"fuzzy_threshold": 101}, (422,)),
            ("validation-recon-period", "post", "/reconciliation/run", {"client_id": cid, "period": "bad-period"}, (422,)),
            ("invalid-recon-status", "get", "/reconciliation/transactions?match_status=bad", None, (422,)),
            ("missing-recon-client", "post", "/reconciliation/run", {"client_id": str(uuid4()), "period": today.strftime("%Y-%m")}, (404,)),
            ("missing-recon-export", "get", f"/reconciliation/export/{uuid4()}", None, (404,)),
            ("not-found-client", "get", f"/clients/{uuid4()}", None, (404,)),
            ("invalid-doc-type", "post", "/documents/upload-url", {"client_id": cid, "doc_type": "exe"}, (400, 500)),
            ("invalid-doc-extension", "post", "/documents/upload-url", {"client_id": cid, "doc_type": "invoice", "filename": "payload.exe"}, (422,)),
            ("invalid-doc-filter-status", "get", "/documents?status=unknown", None, (422,)),
            ("invalid-doc-filter-type", "get", "/documents?doc_type=unknown", None, (422,)),
            ("invalid-doc-client", "post", "/documents/upload-url", {"client_id": str(uuid4()), "doc_type": "invoice", "filename": "invoice.pdf"}, (404,)),
            ("valid-doc-upload-url", "post", "/documents/upload-url", {"client_id": cid, "doc_type": "invoice", "filename": "invoice.pdf"}, (201, 503)),
            ("msme-missing-vendor", "post", "/msme/vendors", {"client_id": cid, "udyam_category": "micro"}, (400,)),
        ]
        for feature, method, path, payload, expected in negative_cases:
            kwargs = {"json": payload} if payload is not None else {}
            response = getattr(self.client, method)(path, **kwargs)
            if response.status_code not in expected:
                self.record_failure(feature, f"Expected controlled error {expected}", response=response)

    def write_report(self):
        REPORT_DIR.mkdir(exist_ok=True)
        report = {
            "run_id": self.run_id,
            "companies_requested": self.companies,
            "created": self.created,
            "failure_count": len(self.failures),
            "gap_count": len(self.gaps),
            "failures": self.failures,
            "scale_gaps": self.gaps,
            "slowest": sorted(self.timings, key=lambda row: row["seconds"], reverse=True)[:20],
            "timings": self.timings,
        }
        json_path = REPORT_DIR / f"stress-report-{self.run_id}.json"
        md_path = REPORT_DIR / f"stress-report-{self.run_id}.md"
        json_path.write_text(json.dumps(report, indent=2, default=as_json), encoding="utf-8")
        lines = [
            f"# Stress Report {self.run_id}",
            "",
            f"- Companies seeded: {self.companies}",
            f"- Failures: {len(self.failures)}",
            f"- Scale/product gaps: {len(self.gaps)}",
            "",
            "## Seeded Records",
            *[f"- {key}: {value}" for key, value in sorted(self.created.items())],
            "",
            "## Failures",
        ]
        lines.extend([f"- {f['feature']}: {f['detail']} ({f.get('status_code', f.get('error', ''))})" for f in self.failures] or ["- None"])
        lines.extend(["", "## Scale/Product Gaps"])
        lines.extend([f"- {g['feature']}: {g['detail']} Observed: {g.get('observed')}" for g in self.gaps] or ["- None"])
        lines.extend(["", "## Slowest Checks"])
        lines.extend([f"- {row['feature']}: {row['seconds']}s" for row in report["slowest"]])
        md_path.write_text("\n".join(lines), encoding="utf-8")
        print(json.dumps({"json_report": str(json_path), "markdown_report": str(md_path), "failures": len(self.failures), "gaps": len(self.gaps)}, indent=2))

    def run(self):
        self.timed("setup tenant", self.setup_tenant)
        self.timed("seed synthetic data", self.seed)
        self.timed("auth and organization tests", self.run_auth_org_tests)
        self.timed("api feature tests", self.run_feature_tests)
        self.write_report()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--companies", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260618)
    args = parser.parse_args()
    StressRun(args.companies, args.seed).run()


if __name__ == "__main__":
    main()
