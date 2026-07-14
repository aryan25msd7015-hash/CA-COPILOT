from datetime import date, timedelta
from types import SimpleNamespace

from app.engines.automation_engines import (
    analyze_debtors, analyze_stock, check_rfp_eligibility, compute_drawing_power,
    compute_lease_schedule, deadline_risk_score, extract_certificate_fields,
    extract_lease_data, msme_violation_values, parse_udyam_certificate,
)


def test_deadline_risk_combines_all_signals():
    score = deadline_risk_score(date.today() + timedelta(days=1), False, 3, True, 40)
    assert score == 10


def test_udyam_parser_extracts_required_fields():
    result = parse_udyam_certificate(
        "UDYAM-MH-19-0123456\nSMALL ENTERPRISE\n"
        "Name of Enterprise: Rapid Supplies LLP\n27AAACR3333C1Z3"
    )
    assert result["udyam_category"] == "small"
    assert result["vendor_gstin"] == "27AAACR3333C1Z3"


def test_msme_violation_uses_45_day_window():
    result = msme_violation_values(date.today() - timedelta(days=60), 100000)
    assert result["violated"] is True
    assert result["days_overdue"] == 15
    assert result["disallowance_amount"] == 100000


def test_drawing_power_excludes_old_stock_and_debtors():
    stock = analyze_stock([
        SimpleNamespace(sku="fresh", stock_value=100000, last_movement_date=date.today() - timedelta(days=10)),
        SimpleNamespace(sku="old", stock_value=50000, last_movement_date=date.today() - timedelta(days=200)),
    ], {"stock_age_cutoff_days": 180, "stock_margin": .25})
    debtors = analyze_debtors([
        SimpleNamespace(debtor_name="current", outstanding=100000, invoice_date=date.today() - timedelta(days=30), payment_history_score=90),
        SimpleNamespace(debtor_name="old", outstanding=50000, invoice_date=date.today() - timedelta(days=100), payment_history_score=80),
    ], {"debtor_age_cutoff_days": 90, "debtor_margin": .25})
    assert stock["eligible_stock"] == 100000
    assert debtors["eligible_debtors"] == 100000
    assert compute_drawing_power(stock, debtors, 10000, {"creditor_deduction": True}, 500000) == 140000


def test_certificate_extractor_computes_working_capital():
    result = extract_certificate_fields(
        "Current assets: INR 5,000,000\nCurrent liabilities: INR 2,500,000",
        "working_capital",
    )
    assert result["net_working_capital"] == 2500000
    assert result["current_ratio"] == 2


def test_lease_schedule_reaches_zero_liability():
    lease = extract_lease_data("", {
        "lease_term_months": 12, "base_rent_monthly": 10000,
        "incremental_borrowing_rate_pct": 9, "rent_free_period_months": 0,
    })
    result = compute_lease_schedule(lease)
    assert len(result["schedule"]) == 12
    assert result["schedule"][-1]["lease_liability"] == 0


def test_rfp_checker_uses_only_stored_credentials():
    creds = SimpleNamespace(
        founding_year=date.today().year - 12, gross_fee_receipts_fy1=12000000,
        gross_fee_receipts_fy2=12000000, gross_fee_receipts_fy3=12000000,
        total_staff=25, peer_review_status="valid", firm_name="Demo Firm",
    )
    result = check_rfp_eligibility(
        "Minimum 10 years experience, turnover INR 10000000, at least 20 staff, valid peer review.",
        creds,
    )
    assert result["overall_eligible"] is True
    assert len(result["criteria"]) == 4
