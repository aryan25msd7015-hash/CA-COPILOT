# CA Copilot Tally Connector

This lightweight connector pushes Tally voucher data into the CA Copilot Autopilot backend.

## Quick start with a Tally CSV export

1. In TallyPrime, export the purchase register or voucher register to CSV.
2. Set these environment variables in PowerShell:

```powershell
$env:CA_COPILOT_API_URL = "http://localhost:8000"
$env:CA_COPILOT_ACCESS_TOKEN = "<access token from login>"
$env:CA_COPILOT_CLIENT_ID = "<client id from CA Copilot>"
```

3. Run:

```powershell
python .\tally_sync_connector.py --csv .\purchase-register.csv --period 2026-06
```

## Direct Tally HTTP mode

If TallyPrime is running with HTTP enabled, this can fetch purchase vouchers from
`http://localhost:9000` and push them to the same backend.

```powershell
$env:TALLY_URL = "http://localhost:9000"
python .\tally_sync_connector.py --from-tally --from-date 20260401 --to-date 20260630 --period 2026-06
```

The backend normalizes common Tally headers such as `Voucher No`, `Vch No.`,
`Date`, `Party Name`, `Particulars`, `GSTIN/UIN of Party`, `Amount`, and
`Tax Amount`.
