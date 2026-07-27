"""Tests for HAE-5 human-auditor assertion precision."""
from datetime import date, timedelta

from app.engines.audit_assertions_engine import (
    compute_materiality,
    infer_period_end,
    run_assertion_procedures,
    assertion_scores_map,
)
from app.engines.audit_bandit import adaptive_sample_plan
from app.engines.hybrid_audit_engine import score_transactions


def _rows():
    pe = date(2026, 3, 31)
    rows = []
    for i in range(20):
        rows.append({
            "id": f"t{i}",
            "org_id": "org",
            "client_id": "c1",
            "vendor_gstin": "27AAAAA0001A1Z5" if i < 15 else "27AAAAA0002A1Z5",
            "vendor_name": "Vendor A" if i < 15 else "Vendor B",
            "invoice_no": f"INV-{100 + i}",
            "amount": 12000 + i * 500,
            "tax_amount": 2160,
            "date": pe - timedelta(days=40 - i),
            "match_status": "exact" if i % 3 else "unmatched",
            "match_confidence": 90 if i % 3 else 40,
            "fingerprint": f"fp{i}" if i % 2 == 0 else "",
            "fraud_flag": None,
            "audit_meta": {},
        })
    # Cut-off + round amount near period end
    rows.append({
        "id": "cutoff1",
        "org_id": "org",
        "client_id": "c1",
        "vendor_gstin": "27AAAAA0001A1Z5",
        "vendor_name": "Vendor A",
        "invoice_no": "INV-999",
        "amount": 100000,
        "tax_amount": 18000,
        "date": pe - timedelta(days=1),
        "match_status": "unmatched",
        "match_confidence": 20,
        "fingerprint": "",
        "fraud_flag": "Invalid GSTIN",
        "audit_meta": {"po_number": "PO-1"},
    })
    # Threshold gaming
    rows.append({
        "id": "thr1",
        "org_id": "org",
        "client_id": "c1",
        "vendor_gstin": "27BBBBB0001A1Z5",
        "vendor_name": "Vendor C",
        "invoice_no": "INV-888",
        "amount": 49999,
        "tax_amount": 9000,
        "date": pe - timedelta(days=20),
        "match_status": "fuzzy",
        "match_confidence": 55,
        "fingerprint": "fp-thr",
        "fraud_flag": None,
        "audit_meta": {"related_party": True},
    })
    # Invoice sequence gap bait
    rows.append({
        "id": "gap1",
        "org_id": "org",
        "client_id": "c1",
        "vendor_gstin": "27AAAAA0001A1Z5",
        "vendor_name": "Vendor A",
        "invoice_no": "INV-105",  # overlaps sequence style
        "amount": 15000,
        "tax_amount": 2700,
        "date": pe - timedelta(days=10),
        "match_status": "exact",
        "match_confidence": 95,
        "fingerprint": "fp-gap",
        "fraud_flag": None,
        "audit_meta": {},
    })
    return rows, pe


def test_materiality_and_period_end():
    mat = compute_materiality([100000, 200000, 50000])
    assert mat["planning_materiality"] > 0
    assert mat["performance_materiality"] == round(mat["planning_materiality"] * 0.75, 2)
    pe = infer_period_end([date(2026, 2, 1), date(2026, 3, 15)])
    assert pe == date(2026, 3, 31)


def test_assertion_procedures_flag_cutoff_and_existence():
    rows, pe = _rows()
    result = run_assertion_procedures(rows, period_end=pe)
    assert result["period_end"] == pe.isoformat()
    assert result["population"]["count"] == len(rows)
    assert result["materiality"]["planning_materiality"] > 0
    scores = assertion_scores_map(result)
    assert scores["cutoff1"] >= 0.6
    payload = result["transaction_assertions"]["cutoff1"]
    assert "cutoff" in payload["failed_assertions"] or "existence" in payload["failed_assertions"]
    assert payload["evidence"]["recommended_procedures"]
    thr = result["transaction_assertions"]["thr1"]
    assert "classification" in thr["failed_assertions"] or "related_party" in thr["failed_assertions"]


def test_precision_fusion_uses_assertions():
    rows, pe = _rows()
    result = run_assertion_procedures(rows, period_end=pe)
    scored = score_transactions(
        rows,
        assertion_scores=assertion_scores_map(result),
        assertion_payloads=result["transaction_assertions"],
        confidence_scores={k: v["confidence"] for k, v in result["transaction_assertions"].items()},
    )
    cutoff_row = scored[scored["id"] == "cutoff1"].iloc[0]
    normal = scored[scored["id"] == "t1"].iloc[0]
    assert float(cutoff_row["audit_risk_prob"]) >= float(normal["audit_risk_prob"])
    assert float(cutoff_row["assertion_score"]) >= float(normal["assertion_score"])
    assert "assertion_score" in scored.columns
    assert cutoff_row["failed_assertions"]
    assert float(cutoff_row["audit_risk_prob"]) >= 0.7


def test_mus_sample_covers_material_items():
    rows, _ = _rows()
    result = run_assertion_procedures(rows)
    scored = score_transactions(
        rows,
        assertion_scores=assertion_scores_map(result),
        assertion_payloads=result["transaction_assertions"],
    )
    items = []
    for _, row in scored.iterrows():
        items.append({
            "id": row["id"],
            "amount": float(next(r["amount"] for r in rows if r["id"] == row["id"])),
            "audit_risk_prob": float(row["audit_risk_prob"]),
            "failed_assertions": row["failed_assertions"],
            "evidence": row["evidence"],
        })
    mat = result["materiality"]
    plan = adaptive_sample_plan(
        items,
        materiality=mat["planning_materiality"],
        performance_materiality=mat["performance_materiality"],
        clearly_trivial=mat["clearly_trivial"],
        review_budget=10,
    )
    assert plan["selected_count"] > 0
    assert "population_coverage_pct" in plan
    assert "stratum_counts" in plan
    # Material cutoff item must be selected
    selected_ids = {s["id"] for s in plan["sample"]}
    assert "cutoff1" in selected_ids
