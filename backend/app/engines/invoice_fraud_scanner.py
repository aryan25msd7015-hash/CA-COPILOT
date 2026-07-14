"""
Invoice fraud scanner engine.

Validates invoices against:
1. Live GSTIN status via GSTN API (with regex fallback)
2. Tax arithmetic (CGST == SGST intra-state, standard rates, total check)
3. Duplicate fingerprint detection
"""
import re
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Standard GST rates
GST_RATES = [0.0, 0.05, 0.12, 0.18, 0.28]

# GSTIN format regex
GSTIN_FORMAT_RE = re.compile(r'^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$')


def validate_gstin(gstin: str) -> dict:
    """
    Validate GSTIN against the live GST portal API.
    Falls back to format check on timeout / API failure.
    """
    if not gstin:
        return {"valid": False, "error": "Empty GSTIN"}

    try:
        url = f"https://online.mastergstin.com/api/v3.0/search?gstin={gstin}"
        r = requests.get(url, timeout=5)
        data = r.json()
        return {
            "valid":  data.get("status") == "ACTIVE",
            "name":   data.get("tradeNam", ""),
            "state":  data.get("stj", ""),
            "status": data.get("sts", ""),
            "offline": False,
        }
    except Exception as e:
        logger.debug(f"Live GSTIN check failed ({e}), falling back to format check")
        return {
            "valid":   bool(GSTIN_FORMAT_RE.match(gstin)),
            "offline": True,
            "error":   str(e),
        }


def verify_invoice_tax(invoice_data: dict) -> dict:
    """
    Verify tax arithmetic on an invoice.
    Returns {valid: bool, issues: list[str]}
    """
    base  = float(invoice_data.get("taxable_amount") or invoice_data.get("amount") or 0)
    cgst  = float(invoice_data.get("cgst_amount", 0) or 0)
    sgst  = float(invoice_data.get("sgst_amount", 0) or 0)
    igst  = float(invoice_data.get("igst_amount", 0) or 0)
    total = float(invoice_data.get("total_amount") or invoice_data.get("amount") or 0)

    issues: list[str] = []

    # CGST should equal SGST for intra-state (within ₹1 tolerance)
    if cgst > 0 or sgst > 0:
        if abs(cgst - sgst) > 1:
            issues.append(f"CGST ({cgst}) ≠ SGST ({sgst}) — intra-state mismatch")

    # Tax rate should match a standard GST rate
    total_tax = cgst + sgst + igst
    if base > 0 and total_tax > 0:
        actual_rate = total_tax / base
        if not any(abs(actual_rate - r) < 0.005 for r in GST_RATES):
            issues.append(f"Non-standard tax rate: {actual_rate * 100:.1f}%")

    # Total should equal base + taxes (within ₹2)
    expected_total = base + total_tax
    if total > 0 and abs(total - expected_total) > 2:
        issues.append(
            f"Total mismatch: ₹{total:.2f} vs expected ₹{expected_total:.2f}"
        )

    return {"valid": len(issues) == 0, "issues": issues}


def generate_fingerprint(invoice_data: dict) -> str:
    """SHA-256 fingerprint of vendor_gstin|invoice_no|amount|date."""
    key = "|".join([
        str(invoice_data.get("vendor_gstin", "")),
        str(invoice_data.get("invoice_no", "")),
        str(invoice_data.get("amount", "")),
        str(invoice_data.get("date", "")),
    ])
    return hashlib.sha256(key.encode()).hexdigest()


def check_duplicate(fingerprint: str, client_id: str, db) -> bool:
    """Check if a transaction with the same fingerprint already exists."""
    from app.models.transaction import Transaction
    return db.query(Transaction).filter(
        Transaction.client_id == client_id,
        Transaction.fingerprint == fingerprint,
    ).first() is not None


def scan_invoice(transaction_id: str, db) -> dict:
    """
    Run all fraud checks on a transaction.
    Sets transaction.fraud_flag if any check fails.
    Returns a dict summarising results.
    """
    from app.models.transaction import Transaction

    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        return {"error": "Transaction not found"}

    failures: list[str] = []

    # 1. GSTIN validation
    if txn.vendor_gstin:
        gstin_result = validate_gstin(txn.vendor_gstin)
        if not gstin_result.get("valid"):
            failures.append(f"Invalid GSTIN: {txn.vendor_gstin}")

    # 2. Tax arithmetic from the originating OCR key-value fields.
    kvs = ((txn.document.ocr_json or {}).get("kvs", {}) if txn.document else {})

    def first(*names):
        return next((kvs.get(name) for name in names if kvs.get(name) not in (None, "")), None)

    def number(value):
        try:
            return float(str(value).replace(",", "").replace("₹", "").strip())
        except (TypeError, ValueError):
            return 0.0

    taxable = number(first("SubTotal", "TaxableAmount", "TaxableValue"))
    total = number(first("InvoiceTotal", "TotalAmount")) or float(txn.amount or 0)
    cgst = number(first("CGST", "CGSTAmount"))
    sgst = number(first("SGST", "SGSTAmount"))
    igst = number(first("IGST", "IGSTAmount"))
    if not any((cgst, sgst, igst)) and txn.tax_amount:
        igst = float(txn.tax_amount)
    if taxable and total:
        tax_result = verify_invoice_tax({
            "taxable_amount": taxable,
            "cgst_amount": cgst,
            "sgst_amount": sgst,
            "igst_amount": igst,
            "total_amount": total,
        })
        failures.extend(tax_result["issues"])

    # 3. Duplicate detection
    if txn.fingerprint:
        dup_exists = db.query(Transaction).filter(
            Transaction.client_id == txn.client_id,
            Transaction.fingerprint == txn.fingerprint,
            Transaction.id != txn.id,
        ).first()
        if dup_exists:
            failures.append(f"Duplicate invoice (matches transaction {dup_exists.id})")

    txn.fraud_flag = "; ".join(failures) if failures else None
    txn.fraud_scanned_at = datetime.now(timezone.utc)
    review_status = getattr(txn, "fraud_review_status", None)
    if failures and review_status not in {"confirmed", "needs_followup"}:
        txn.fraud_review_status = "open"
    if not failures:
        txn.fraud_review_status = "cleared"
        txn.fraud_review_note = None
    db.commit()

    return {
        "transaction_id": transaction_id,
        "fraud_flag": txn.fraud_flag,
        "failures": failures,
        "clean": len(failures) == 0,
    }
