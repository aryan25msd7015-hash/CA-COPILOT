"""
Tally ERP CSV normalizer.

Handles both Tally Prime and Tally ERP 9 CSV export formats and normalises
them to canonical column names used throughout the platform.

Canonical columns: invoice_no, vendor_name, vendor_gstin, amount, date
"""
import re
import io
import csv
from datetime import date as date_type
from typing import Optional

import pandas as pd

# ── Column header mapping ─────────────────────────────────────────────────────
TALLY_MAP: dict[str, str] = {
    # Tally Prime
    "Voucher No":           "invoice_no",
    "Date":                 "date",
    "Party Name":           "vendor_name",
    "Amount":               "amount",
    "GSTIN/UIN of Party":   "vendor_gstin",
    "Tax Amount":           "tax_amount",
    # Tally ERP 9
    "Vch No.":              "invoice_no",
    "Vch Date":             "date",
    "Particulars":          "vendor_name",
    "Debit":                "amount",
    "GSTIN":                "vendor_gstin",
    "GST Amount":           "tax_amount",
    # Additional common variants
    "Invoice No":           "invoice_no",
    "Invoice Number":       "invoice_no",
    "Party GSTIN":          "vendor_gstin",
    "Taxable Amount":       "amount",
    "Bill No":              "invoice_no",
    "Bill Number":          "invoice_no",
}

_SUFFIX_RE = re.compile(
    r'\b(PVT\.?|LTD\.?|PRIVATE|LIMITED|LLP|CORP\.?|CORPORATION|INC\.?|CO\.?)\b',
    flags=re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r'\s+')


def _normalize_vendor_name(name: str) -> str:
    name = str(name).upper().strip()
    name = _SUFFIX_RE.sub(' ', name)
    name = _WHITESPACE_RE.sub(' ', name).strip()
    return name


def _parse_amount(value) -> Optional[float]:
    if pd.isna(value):
        return None
    cleaned = str(value).replace(',', '').replace('₹', '').strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_tally(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise a raw Tally CSV DataFrame to canonical column names.

    Raises ValueError if required canonical columns are missing after rename.
    """
    df = df.rename(columns=TALLY_MAP)

    required = {"invoice_no", "amount", "date"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns after normalisation: {missing}")

    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    df["amount"] = df["amount"].apply(_parse_amount)

    if "vendor_name" in df.columns:
        df["vendor_name"] = df["vendor_name"].apply(
            lambda x: _normalize_vendor_name(x) if pd.notna(x) else None
        )

    if "tax_amount" in df.columns:
        df["tax_amount"] = df["tax_amount"].apply(_parse_amount)

    df = df.dropna(subset=["amount"])
    df = df.reset_index(drop=True)
    return df


def to_canonical_csv(transactions: list[dict]) -> str:
    """Serialise transaction dicts to canonical CSV (invoice_no, vendor_name, vendor_gstin, amount, date)."""
    canonical_fields = ["invoice_no", "vendor_name", "vendor_gstin", "amount", "date"]
    output = io.StringIO()
    writer = csv.DictWriter(
        output, fieldnames=canonical_fields, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    for txn in transactions:
        row = {}
        for field in canonical_fields:
            value = txn.get(field, "")
            if isinstance(value, date_type):
                value = value.strftime("%d/%m/%Y")
            elif hasattr(value, 'strftime'):  # pandas Timestamp
                value = value.strftime("%d/%m/%Y")
            elif value is None or (isinstance(value, float) and pd.isna(value)):
                value = ""
            row[field] = str(value)
        writer.writerow(row)
    return output.getvalue()
