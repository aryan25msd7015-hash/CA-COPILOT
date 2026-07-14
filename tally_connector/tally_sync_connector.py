"""Push Tally voucher data to the CA Copilot Autopilot API.

This script is intentionally small so firms can run it on the Windows machine
where TallyPrime is installed.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import requests


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def tally_xml_request(from_date: str, to_date: str) -> str:
    return f"""
<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Export Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <EXPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>Voucher Register</REPORTNAME>
        <STATICVARIABLES>
          <SVFROMDATE>{from_date}</SVFROMDATE>
          <SVTODATE>{to_date}</SVTODATE>
          <VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>
          <EXPLODEFLAG>Yes</EXPLODEFLAG>
          <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
        </STATICVARIABLES>
      </REQUESTDESC>
    </EXPORTDATA>
  </BODY>
</ENVELOPE>
""".strip()


def fetch_tally_vouchers(tally_url: str, from_date: str, to_date: str) -> list[dict[str, Any]]:
    response = requests.post(
        tally_url,
        data=tally_xml_request(from_date, to_date).encode("utf-8"),
        headers={"Content-Type": "text/xml"},
        timeout=60,
    )
    response.raise_for_status()
    root = ET.fromstring(response.text)
    records: list[dict[str, Any]] = []
    for voucher in root.findall(".//VOUCHER"):
        amount = ""
        tax_amount = ""
        for ledger in voucher.findall(".//ALLLEDGERENTRIES.LIST"):
            ledger_name = (ledger.findtext("LEDGERNAME") or "").lower()
            ledger_amount = ledger.findtext("AMOUNT") or ""
            if any(word in ledger_name for word in ("igst", "cgst", "sgst", "gst")):
                tax_amount = ledger_amount.lstrip("-")
            elif not amount:
                amount = ledger_amount.lstrip("-")
        records.append({
            "Voucher No": voucher.findtext("VOUCHERNUMBER") or voucher.findtext("VOUCHERKEY") or "",
            "Date": voucher.findtext("DATE") or "",
            "Party Name": voucher.findtext("PARTYLEDGERNAME") or "",
            "GSTIN/UIN of Party": voucher.findtext(".//PARTYGSTIN") or voucher.findtext(".//GSTREGISTRATIONNUMBER") or "",
            "Amount": amount,
            "Tax Amount": tax_amount,
        })
    return [record for record in records if record.get("Voucher No")]


def push_records(api_url: str, access_token: str, client_id: str, records: list[dict[str, Any]], source_name: str, period: str | None):
    endpoint = f"{api_url.rstrip('/')}/autopilot/tally/sync"
    response = requests.post(
        endpoint,
        json={
            "client_id": client_id,
            "source_name": source_name,
            "period": period,
            "records": records,
        },
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=90,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Tally data to CA Copilot Autopilot")
    parser.add_argument("--csv", type=Path, help="Path to a Tally CSV export")
    parser.add_argument("--from-tally", action="store_true", help="Fetch vouchers from local Tally HTTP XML API")
    parser.add_argument("--from-date", default="", help="Tally date in YYYYMMDD format")
    parser.add_argument("--to-date", default="", help="Tally date in YYYYMMDD format")
    parser.add_argument("--period", default=None, help="Reporting period, e.g. 2026-06")
    parser.add_argument("--source-name", default="TallyPrime")
    args = parser.parse_args()

    api_url = os.environ.get("CA_COPILOT_API_URL", "http://localhost:8000")
    access_token = os.environ.get("CA_COPILOT_ACCESS_TOKEN")
    client_id = os.environ.get("CA_COPILOT_CLIENT_ID")
    if not access_token or not client_id:
        print("Set CA_COPILOT_ACCESS_TOKEN and CA_COPILOT_CLIENT_ID first.", file=sys.stderr)
        return 2

    if args.csv:
        records = read_csv(args.csv)
    elif args.from_tally:
        if not args.from_date or not args.to_date:
            print("--from-date and --to-date are required for --from-tally.", file=sys.stderr)
            return 2
        records = fetch_tally_vouchers(os.environ.get("TALLY_URL", "http://localhost:9000"), args.from_date, args.to_date)
    else:
        print("Use either --csv or --from-tally.", file=sys.stderr)
        return 2

    result = push_records(api_url, access_token, client_id, records, args.source_name, args.period)
    print(
        f"Synced {result['sync_run']['records_imported']} new records "
        f"({result['sync_run']['records_failed']} failed). "
        f"Autopilot candidates: {result['autopilot_refresh']['candidate_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
