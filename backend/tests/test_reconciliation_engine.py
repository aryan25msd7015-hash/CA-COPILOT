import pandas as pd

from app.engines.reconciliation_engine import reconcile
from app.tasks.reconciliation_tasks import _period_bounds


def test_exact_match_does_not_reuse_gstr2b_row():
    purchase = pd.DataFrame([
        {"id": "p1", "vendor_gstin": "27ABCDE1234F1Z5", "invoice_no": "A1", "vendor_name": "ACME", "amount": 100, "date": "01/06/2026"},
        {"id": "p2", "vendor_gstin": "27ABCDE1234F1Z5", "invoice_no": "A1", "vendor_name": "ACME", "amount": 100, "date": "01/06/2026"},
    ])
    gstr2b = pd.DataFrame([
        {"id": "g1", "vendor_gstin": "27ABCDE1234F1Z5", "invoice_no": "A1", "vendor_name": "ACME", "amount": 100, "date": "01/06/2026"},
    ])

    matched, unmatched = reconcile(purchase, gstr2b)

    assert len(matched) == 1
    assert len(unmatched) == 1


def test_period_bounds_support_ui_and_api_formats():
    assert _period_bounds("Jun 2026") == _period_bounds("Jun-2026")
    assert _period_bounds("2026-06") == _period_bounds("Jun 2026")
    assert _period_bounds("not-a-period") is None
