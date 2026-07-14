from datetime import date

from app.engines.autopilot_engine import normalize_tally_records, transaction_fingerprint


def test_normalize_tally_records_accepts_common_tally_headers():
    rows, failed = normalize_tally_records([
        {
            "Voucher No": "pur-101",
            "Date": date.today().strftime("%d/%m/%Y"),
            "Party Name": "Rapid Supplies LLP",
            "GSTIN/UIN of Party": "27aaacr3333c1z3",
            "Amount": "49,500",
            "Tax Amount": "8,910",
        },
        {"Voucher No": "", "Amount": "10"},
    ])

    assert failed[0]["reason"] == "invoice_no, amount and date are required"
    assert rows[0]["invoice_no"] == "PUR-101"
    assert rows[0]["vendor_gstin"] == "27AAACR3333C1Z3"
    assert rows[0]["amount"] == 49500
    assert rows[0]["tax_amount"] == 8910


def test_tally_transaction_fingerprint_is_stable():
    row = {"invoice_no": "PUR-101", "vendor_gstin": "27AAACR3333C1Z3", "amount": 49500, "date": date(2026, 6, 5)}

    assert transaction_fingerprint("org", "client", "Tally", row) == transaction_fingerprint("org", "client", "Tally", row)
    assert transaction_fingerprint("org", "client", "Tally", row) != transaction_fingerprint("org", "client", "Other", row)
