"""Smoke-test all CA Copilot frontend routes over HTTP.

This no-dependency harness validates that the production Next server returns
non-empty HTML for every app route. It catches broken builds, missing routes,
500s, and blank server output without requiring browser automation packages.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

BASE = "http://localhost:3000"
OUT = Path(__file__).with_name("frontend_route_smoke_report.json")

ROUTES = [
    "/",
    "/login",
    "/register",
    "/anomalies",
    "/audit",
    "/autopilot",
    "/benchmarking",
    "/billing",
    "/certificates",
    "/clients",
    "/deadlines",
    "/documents",
    "/drawing-power",
    "/imports",
    "/invoices",
    "/leases",
    "/msme",
    "/notices",
    "/portal",
    "/query",
    "/reconciliation",
    "/reports",
    "/rfp",
    "/secretarial",
    "/team",
    "/timesheets",
    "/vault",
    "/whatsapp",
    "/work",
]


def fetch(path: str):
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(BASE + path, timeout=15) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, body, round((time.perf_counter() - started) * 1000, 2), None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body, round((time.perf_counter() - started) * 1000, 2), str(exc)
    except Exception as exc:  # noqa: BLE001 - report any route smoke failure
        return 0, "", round((time.perf_counter() - started) * 1000, 2), str(exc)


def main():
    rows = []
    failures = []
    latencies = []
    for route in ROUTES:
        status, body, ms, error = fetch(route)
        latencies.append(ms)
        has_html = "<html" in body.lower()
        has_next = "__next" in body or "self.__next_f" in body
        non_empty = len(body.strip()) > 500
        passed = status == 200 and has_html and has_next and non_empty
        row = {
            "route": route,
            "status": status,
            "bytes": len(body.encode("utf-8")),
            "latency_ms": ms,
            "has_html": has_html,
            "has_next_payload": has_next,
            "non_empty": non_empty,
            "passed": passed,
            "error": error,
        }
        rows.append(row)
        if not passed:
            failures.append(row)

    report = {
        "generated_at": str(date.today()),
        "base_url": BASE,
        "routes": len(ROUTES),
        "passed": sum(1 for row in rows if row["passed"]),
        "failed": len(failures),
        "latency_ms": {
            "min": min(latencies),
            "max": max(latencies),
            "avg": round(sum(latencies) / len(latencies), 2),
        },
        "failures": failures,
        "results": rows,
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("routes", "passed", "failed", "latency_ms")} | {"report": str(OUT)}, indent=2))


if __name__ == "__main__":
    main()
