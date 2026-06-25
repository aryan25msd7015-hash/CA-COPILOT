"""Unit tests for the Tally CSV normalizer."""
import io
import pytest
import pandas as pd
from app.engines.tally_normalizer import normalize_tally, to_canonical_csv


def prime_df(rows=None):
    defaults = {
        "Voucher No": "INV001", "Date": "01/04/2024",
        "Party Name": "ACME PRIVATE LIMITED", "Amount": "10000.00",
        "GSTIN/UIN of Party": "27ABCDE1234F1Z5",
    }
    return pd.DataFrame([{**defaults, **(r or {})} for r in (rows or [{}])])


def erp9_df(rows=None):
    defaults = {
        "Vch No.": "V001", "Vch Date": "01/04/2024",
        "Particulars": "BETA LTD", "Debit": "5,000",
        "GSTIN": "29AABCT1332L1ZD",
    }
    return pd.DataFrame([{**defaults, **(r or {})} for r in (rows or [{}])])


# ── Tally Prime ───────────────────────────────────────────────────────────────
def test_prime_headers_renamed():
    df = normalize_tally(prime_df())
    assert {"invoice_no", "vendor_name", "amount", "date"}.issubset(df.columns)


def test_prime_amount_parsed():
    df = normalize_tally(prime_df([{"Amount": "1,23,456.78"}]))
    assert df.iloc[0]["amount"] == pytest.approx(123456.78)


def test_prime_date_parsed_dayfirst():
    df = normalize_tally(prime_df([{"Date": "15/08/2024"}]))
    assert df.iloc[0]["date"].month == 8
    assert df.iloc[0]["date"].day == 15


def test_prime_vendor_name_normalised():
    df = normalize_tally(prime_df([{"Party Name": "Acme Private Limited"}]))
    assert df.iloc[0]["vendor_name"] == "ACME"


def test_prime_vendor_llp_stripped():
    df = normalize_tally(prime_df([{"Party Name": "Tata Consultancy LLP"}]))
    assert "LLP" not in df.iloc[0]["vendor_name"]


# ── Tally ERP 9 ───────────────────────────────────────────────────────────────
def test_erp9_headers_renamed():
    df = normalize_tally(erp9_df())
    assert {"invoice_no", "vendor_name", "amount"}.issubset(df.columns)


def test_erp9_amount_with_commas():
    df = normalize_tally(erp9_df([{"Debit": "50,000"}]))
    assert df.iloc[0]["amount"] == pytest.approx(50000.0)


# ── Row dropping ──────────────────────────────────────────────────────────────
def test_unparseable_amount_dropped():
    df = prime_df([{"Amount": "10000"}, {"Amount": "N/A"}, {"Amount": "5000"}])
    assert len(normalize_tally(df)) == 2


def test_all_bad_amounts_empty():
    df = prime_df([{"Amount": "bad"}, {"Amount": ""}])
    assert len(normalize_tally(df)) == 0


# ── Round-trip ────────────────────────────────────────────────────────────────
def test_round_trip():
    original = prime_df([{
        "Voucher No": "INV001", "Party Name": "Delta Corp Ltd",
        "Amount": "25000", "Date": "10/04/2024",
        "GSTIN/UIN of Party": "27XYZPQ5678R1Z3",
    }])
    parsed = normalize_tally(original)
    csv_text = to_canonical_csv(parsed.to_dict("records"))
    re_df = pd.read_csv(io.StringIO(csv_text))
    re_df["date"] = pd.to_datetime(re_df["date"], dayfirst=True, errors="coerce")
    re_df["amount"] = pd.to_numeric(re_df["amount"], errors="coerce")
    assert re_df.iloc[0]["invoice_no"] == parsed.iloc[0]["invoice_no"]
    assert re_df.iloc[0]["amount"] == pytest.approx(float(parsed.iloc[0]["amount"]))


# ── Missing required columns ──────────────────────────────────────────────────
def test_missing_columns_raises():
    with pytest.raises(ValueError, match="Missing required columns"):
        normalize_tally(pd.DataFrame([{"RandomCol": "value"}]))


# ── to_canonical_csv ──────────────────────────────────────────────────────────
def test_canonical_csv_has_headers():
    csv_text = to_canonical_csv([{"invoice_no": "INV1", "amount": 100, "date": "2024-04-01"}])
    assert "invoice_no" in csv_text and "amount" in csv_text


def test_canonical_csv_extra_fields_ignored():
    csv_text = to_canonical_csv([{"invoice_no": "X", "amount": 50, "extra_field": "ignored"}])
    assert "extra_field" not in csv_text
