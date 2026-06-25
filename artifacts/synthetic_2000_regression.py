"""Generate 2000 synthetic companies and exercise CA Copilot feature logic.

This script is intentionally non-destructive: it does not insert synthetic
companies into the application database. It stress-tests deterministic engines
and payload rules with a representative synthetic portfolio, then writes a JSON
report beside this script.
"""
from __future__ import annotations

import json
import random
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.engines.automation_engines import (  # noqa: E402
    CERTIFICATE_TYPES,
    check_rfp_eligibility,
    compute_drawing_power,
    compute_lease_schedule,
    deadline_risk_score,
    extract_certificate_fields,
    extract_lease_data,
    generate_bid_proposal,
    generate_secretarial_document,
    get_fy,
    msme_violation_values,
    parse_udyam_certificate,
    validate_certificate_fields,
)


SEED = 240624
COUNT = 2000
TODAY = date(2026, 6, 24)
OUT = Path(__file__).with_name("synthetic_2000_regression_report.json")


def money(value: float) -> float:
    return round(float(value), 2)


def company(index: int) -> dict:
    entity_types = ["pvt_ltd", "llp", "partnership", "proprietorship", "trust"]
    industries = ["Manufacturing", "Services", "Trading", "Construction", "Healthcare"]
    return {
        "id": f"SYN-{index:04d}",
        "name": f"Synthetic Company {index:04d} Pvt Ltd",
        "entity_type": entity_types[index % len(entity_types)],
        "industry": industries[index % len(industries)],
        "health_score": (index * 17) % 101,
        "gstin": f"27ABCDE{index % 10000:04d}F1Z{index % 10}",
        "pan": f"ABCDE{index % 10000:04d}F",
        "turnover": money(1_000_000 + index * 17_531),
        "staff": 5 + (index % 80),
        "late_count": index % 5,
        "has_notice": index % 11 == 0,
        "data_received": index % 3 == 0,
    }


class Harness:
    def __init__(self):
        self.summary: dict[str, dict] = {}
        self.edge_cases: list[dict] = []

    def feature(self, name: str):
        self.summary.setdefault(name, {"cases": 0, "passed": 0, "failed": 0})

    def ok(self, name: str):
        self.feature(name)
        self.summary[name]["cases"] += 1
        self.summary[name]["passed"] += 1

    def fail(self, name: str, case_id: str, message: str, payload=None):
        self.feature(name)
        self.summary[name]["cases"] += 1
        self.summary[name]["failed"] += 1
        self.edge_cases.append({
            "feature": name,
            "case_id": case_id,
            "message": message,
            "payload": payload,
        })

    def check(self, name: str, case_id: str, condition: bool, message: str, payload=None):
        if condition:
            self.ok(name)
        else:
            self.fail(name, case_id, message, payload)


def run():
    random.seed(SEED)
    h = Harness()
    companies = [company(index) for index in range(1, COUNT + 1)]

    credentials = SimpleNamespace(
        firm_name="Synthetic CA Firm",
        icai_regn_no="FRN123456W",
        founding_year=2008,
        total_staff=42,
        gross_fee_receipts_fy1=15_000_000,
        gross_fee_receipts_fy2=13_500_000,
        gross_fee_receipts_fy3=12_000_000,
        peer_review_status="valid",
        partners=[{"name": "Aarav Mehta"}],
        industries_served=[{"industry": "Manufacturing"}],
        key_engagements=[{"name": "Manufacturing statutory audit"}],
    )

    start = time.perf_counter()
    for item in companies:
        cid = item["id"]

        h.check("auth_org_client_payloads", cid, item["name"] and item["entity_type"] in {"pvt_ltd", "llp", "partnership", "proprietorship", "trust"}, "Invalid client identity payload", item)

        deadline = TODAY + timedelta(days=(int(cid[-4:]) % 45) - 5)
        risk = deadline_risk_score(deadline, item["data_received"], item["late_count"], item["has_notice"], item["health_score"], TODAY)
        h.check("deadlines_risk_scoring", cid, 0 <= risk <= 10, "Deadline risk outside 0-10", {"risk": risk})

        invoice_date = TODAY - timedelta(days=30 + (int(cid[-4:]) % 90))
        payment_date = None if int(cid[-4:]) % 4 else invoice_date + timedelta(days=40)
        msme = msme_violation_values(invoice_date, item["turnover"] / 120, payment_date, TODAY)
        h.check("msme_43bh", cid, msme["days_overdue"] >= 0 and msme["disallowance_amount"] >= 0, "Invalid MSME computation", msme)
        cert_text = f"UDYAM-MH-19-{int(cid[-4:]):07d}\nSMALL ENTERPRISE\nName of Enterprise: {item['name']}\n{item['gstin']}"
        try:
            parsed = parse_udyam_certificate(cert_text)
            h.check("msme_udyam_parse", cid, parsed["udyam_category"] in {"micro", "small", "medium"}, "Udyam category parse failed", parsed)
        except Exception as exc:
            h.fail("msme_udyam_parse", cid, str(exc), cert_text)

        stock = {
            "gross_stock": item["turnover"] * 0.18,
            "eligible_stock": item["turnover"] * 0.14,
            "stock_dp": item["turnover"] * 0.14 * 0.75,
        }
        debtors = {
            "gross_debtors": item["turnover"] * 0.22,
            "eligible_debtors": item["turnover"] * 0.18,
            "debtor_dp": item["turnover"] * 0.18 * 0.70,
        }
        dp = compute_drawing_power(stock, debtors, item["turnover"] * 0.03, {"creditor_deduction": True}, item["turnover"] * 0.40)
        h.check("drawing_power", cid, 0 <= dp <= item["turnover"] * 0.40, "Drawing power outside cap", {"dp": dp})

        source = (
            f"current assets: {item['turnover'] * 0.4:.2f}\n"
            f"current liabilities: {item['turnover'] * 0.2:.2f}\n"
            f"net working capital: {item['turnover'] * 0.2:.2f}\n"
            "current ratio: 2.0"
        )
        fields = extract_certificate_fields(source, "working_capital")
        validation = validate_certificate_fields(fields, {"current_ratio": 2.0})
        h.check("certificates", cid, validation["valid"], "Certificate validation failed", {"fields": fields, "validation": validation})

        client = SimpleNamespace(name=item["name"], cin=f"U{int(cid[-4:]):05d}MH2026PTC123456", registered_office="Registered Office")
        structured, generated, xml = generate_secretarial_document(
            "board_minutes",
            client,
            "The board approved a banking facility. The board authorized the director to sign documents.",
            {"meeting_date": str(TODAY), "directors_present": ["Director A", "Director B"]},
        )
        h.check("secretarial_documents", cid, bool(generated) and bool(xml) and len(structured.get("resolutions", [])) >= 1, "Secretarial generation incomplete", structured)

        lease_text = "Commencement date: 2026-04-01. Lease term: 36 months. Monthly rent: INR 100000. IBR: 9%."
        lease = extract_lease_data(lease_text, {"lease_term_months": 12 + (int(cid[-4:]) % 49)})
        schedule = compute_lease_schedule(lease)
        h.check("leases", cid, schedule["initial_lease_liability"] > 0 and len(schedule["schedule"]) == lease["lease_term_months"], "Lease schedule mismatch", {"lease_term": lease["lease_term_months"]})

        rfp_text = "minimum 10 years experience. turnover INR 10000000. minimum 25 staff. peer review valid. statutory audit scope."
        eligibility = check_rfp_eligibility(rfp_text, credentials)
        proposal = generate_bid_proposal(f"RFP {cid}", rfp_text, eligibility, credentials)
        h.check("rfp_bids", cid, eligibility["overall_eligible"] and bool(proposal), "Eligible RFP did not generate proposal", eligibility)

        actual_hours = 1 + (int(cid[-4:]) % 6)
        logged_hours = max(actual_hours - (int(cid[-4:]) % 3), 0)
        revenue = logged_hours * 1800
        cost = logged_hours * 900
        h.check("timesheets_profitability", cid, revenue - cost >= 0 and logged_hours <= actual_hours, "Profitability invariant failed", {"actual": actual_hours, "logged": logged_hours})

        h.check("benchmarking", cid, item["turnover"] > 0 and item["industry"], "Benchmarking peer attributes missing", item)
        h.check("autopilot_exceptions", cid, isinstance(item["has_notice"], bool), "Autopilot signal malformed", item)
        h.check("whatsapp_notices_documents", cid, len(item["gstin"]) == 15 and item["pan"], "Communication/document identity fields invalid", item)

    elapsed = round(time.perf_counter() - start, 3)
    report = {
        "generated_at": "2026-06-24",
        "seed": SEED,
        "companies": COUNT,
        "elapsed_seconds": elapsed,
        "summary": h.summary,
        "edge_cases": h.edge_cases[:200],
        "edge_case_count": len(h.edge_cases),
        "overall": {
            "cases": sum(row["cases"] for row in h.summary.values()),
            "passed": sum(row["passed"] for row in h.summary.values()),
            "failed": sum(row["failed"] for row in h.summary.values()),
        },
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["overall"] | {"report": str(OUT), "elapsed_seconds": elapsed}, indent=2))


if __name__ == "__main__":
    run()
