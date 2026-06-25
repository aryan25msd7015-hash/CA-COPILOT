from types import SimpleNamespace
from unittest.mock import MagicMock

from app.engines.invoice_fraud_scanner import generate_fingerprint, scan_invoice, verify_invoice_tax


def test_fingerprint_is_deterministic():
    invoice = {"vendor_gstin": "27ABCDE1234F1Z5", "invoice_no": "A-1", "amount": 118, "date": "2026-06-01"}
    assert generate_fingerprint(invoice) == generate_fingerprint(invoice)


def test_valid_standard_rate_invoice():
    result = verify_invoice_tax({
        "taxable_amount": 100,
        "cgst_amount": 9,
        "sgst_amount": 9,
        "total_amount": 118,
    })
    assert result["valid"]


def test_detects_tax_mismatch():
    result = verify_invoice_tax({
        "taxable_amount": 100,
        "cgst_amount": 9,
        "sgst_amount": 5,
        "total_amount": 114,
    })
    assert not result["valid"]


def test_scan_invoice_uses_document_tax_fields():
    transaction = SimpleNamespace(
        id="transaction-id",
        vendor_gstin=None,
        amount=114,
        tax_amount=14,
        fingerprint=None,
        fraud_flag=None,
        document=SimpleNamespace(ocr_json={"kvs": {
            "TaxableAmount": "100",
            "CGSTAmount": "9",
            "SGSTAmount": "5",
            "InvoiceTotal": "114",
        }}),
    )
    query = MagicMock()
    query.filter.return_value.first.return_value = transaction
    db = MagicMock()
    db.query.return_value = query

    result = scan_invoice("transaction-id", db)

    assert not result["clean"]
    assert "CGST" in transaction.fraud_flag
