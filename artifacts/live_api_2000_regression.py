"""Run a 2000-case live HTTP regression against the local CA Copilot API.

The script uses the demo account and keeps mutations intentionally small. Most
cases are read/validation requests with varied query parameters so the live
routing, auth, serializers, and endpoint guardrails are exercised without
creating thousands of database rows.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

BASE = "http://localhost:8000"
EMAIL = "demo@cacopilot.example.com"
PASSWORD = "DemoPass123"
TOTAL_CASES = 2000
OUT = Path(__file__).with_name("live_api_2000_regression_report.json")


def request(method: str, path: str, token: str | None = None, body=None):
    data = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else None, round((time.perf_counter() - started) * 1000, 2)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = raw
        return exc.code, payload, round((time.perf_counter() - started) * 1000, 2)


def qs(params: dict) -> str:
    return urllib.parse.urlencode({key: value for key, value in params.items() if value not in (None, "")})


def main():
    login_status, login, _ = request("POST", "/auth/login", body={"email": EMAIL, "password": PASSWORD})
    if login_status != 200 or not login or not login.get("access_token"):
        raise SystemExit(f"Login failed: {login_status} {login}")
    token = login["access_token"]

    clients_status, clients, _ = request("GET", "/clients", token)
    if clients_status != 200 or not clients:
        raise SystemExit(f"Client list failed: {clients_status} {clients}")
    client_id = clients[0]["id"]
    month = date.today().strftime("%Y-%m")
    fy = f"{date.today().year if date.today().month >= 4 else date.today().year - 1}-{str((date.today().year if date.today().month >= 4 else date.today().year - 1) + 1)[-2:]}"

    endpoints = [
        ("clients", "GET", "/clients", {}),
        ("client_summary", "GET", f"/clients/{client_id}/summary", {}),
        ("client_health", "GET", f"/clients/{client_id}/health-history", {}),
        ("documents", "GET", "/documents", {"client_id": client_id, "limit": 20}),
        ("reconciliation_transactions", "GET", "/reconciliation/transactions", {"client_id": client_id, "limit": 20}),
        ("reconciliation_config", "GET", f"/reconciliation/config/{client_id}", {}),
        ("deadlines", "GET", "/deadlines", {"client_id": client_id, "limit": 20}),
        ("calendar_overview", "GET", "/calendar/overview", {"days_ahead": 120}),
        ("msme_overview", "GET", "/msme/overview", {"client_id": client_id, "fy": fy}),
        ("msme_vendors", "GET", "/msme/vendors", {"client_id": client_id, "limit": 20}),
        ("drawing_power_overview", "GET", "/drawing-power/overview", {"client_id": client_id, "period": month}),
        ("certificates_overview", "GET", "/certificates/overview", {"client_id": client_id}),
        ("secretarial_overview", "GET", "/secretarial/overview", {"client_id": client_id}),
        ("leases_overview", "GET", "/leases/overview", {"client_id": client_id}),
        ("timesheets_overview", "GET", "/timesheets/overview", {"month": month}),
        ("rfp_overview", "GET", "/rfp/overview", {}),
        ("autopilot_overview", "GET", "/autopilot/overview", {}),
        ("autopilot_exceptions", "GET", "/autopilot/exceptions", {"limit": 20}),
        ("whatsapp_status", "GET", "/whatsapp/status", {"client_id": client_id}),
        ("anomalies_summary", "GET", "/anomalies/summary", {}),
        ("invoices_fraud_summary", "GET", "/invoices/fraud-summary", {}),
        ("query_starters", "GET", "/query/starters", {}),
        ("query_saved", "GET", "/query/saved", {}),
        ("work_overview", "GET", "/work/overview", {"month": month}),
        ("billing_overview", "GET", "/billing/overview", {}),
        ("portal_overview", "GET", "/portal/overview", {}),
        ("team_overview", "GET", "/team/overview", {}),
        ("vault_overview", "GET", "/vault/overview", {}),
        ("imports_overview", "GET", "/imports/overview", {}),
        ("reports_overview", "GET", "/reports/overview", {}),
    ]

    failures = []
    feature_counts: dict[str, dict] = {}
    latencies = []

    for index in range(TOTAL_CASES):
        feature, method, path, params = endpoints[index % len(endpoints)]
        varied = dict(params)
        if "limit" in varied:
            varied["skip"] = index % 3
        url = path + (("?" + qs(varied)) if varied else "")
        status, payload, ms = request(method, url, token)
        latencies.append(ms)
        row = feature_counts.setdefault(feature, {"cases": 0, "passed": 0, "failed": 0})
        row["cases"] += 1
        if 200 <= status < 300:
            row["passed"] += 1
        else:
            row["failed"] += 1
            failures.append({"case": index + 1, "feature": feature, "status": status, "path": url, "payload": payload})

    mutations = []
    controlled = [
        ("invalid_msme_gstin", "POST", "/msme/vendors", {"client_id": client_id, "vendor_name": "Invalid API Vendor", "vendor_gstin": "TOO-LONG-GSTIN-123", "udyam_category": "micro"}, 422),
        ("invalid_activity", "POST", "/timesheets/activities", {"client_id": client_id, "activity_type": "bad_activity", "duration_seconds": 60, "details": {}}, 422),
        ("valid_query", "POST", "/query/ask-now", {"question": "Which clients need attention?", "client_id": client_id}, 200),
    ]
    for name, method, path, body, expected in controlled:
        status, payload, ms = request(method, path, token, body)
        latencies.append(ms)
        ok = status == expected
        mutations.append({"name": name, "status": status, "expected": expected, "passed": ok})
        if not ok:
            failures.append({"case": f"controlled:{name}", "feature": name, "status": status, "path": path, "payload": payload})

    report = {
        "generated_at": str(date.today()),
        "base_url": BASE,
        "cases": TOTAL_CASES,
        "controlled_mutations": len(controlled),
        "summary": feature_counts,
        "mutations": mutations,
        "failures": failures[:100],
        "failure_count": len(failures),
        "latency_ms": {
            "min": min(latencies),
            "max": max(latencies),
            "avg": round(sum(latencies) / len(latencies), 2),
        },
        "overall": {
            "cases": TOTAL_CASES + len(controlled),
            "passed": TOTAL_CASES + sum(1 for row in mutations if row["passed"]) - len([f for f in failures if isinstance(f["case"], int)]),
            "failed": len(failures),
        },
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"overall": report["overall"], "latency_ms": report["latency_ms"], "report": str(OUT)}, indent=2))


if __name__ == "__main__":
    main()
