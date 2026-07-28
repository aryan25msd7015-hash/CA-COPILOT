from datetime import date, timedelta

from app.plugins.layer2_risk_fusion import Layer2RiskFusionPlugin


def _sample_rows(n: int = 12) -> list[dict]:
    rows: list[dict] = []
    for i in range(n):
        rows.append(
            {
                "id": f"txn-{i}",
                "org_id": "org-1",
                "client_id": "client-1",
                "vendor_gstin": f"27AAAAA{i % 4:04d}A1Z5",
                "vendor_name": f"Vendor {i % 4}",
                "invoice_no": f"INV-{i}",
                "amount": 1000 + (i * 2500),
                "tax_amount": 180.0,
                "date": date.today() - timedelta(days=n - i),
                "match_status": "unmatched" if i % 3 == 0 else "exact",
                "fraud_flag": "bad gstin" if i == n - 1 else None,
            }
        )
    rows[-1]["amount"] = 250000.0
    rows[-2]["invoice_no"] = rows[-3]["invoice_no"]
    rows[-2]["vendor_gstin"] = rows[-3]["vendor_gstin"]
    return rows


def test_layer2_plugin_status_contract() -> None:
    plugin = Layer2RiskFusionPlugin(org_id="org-1")
    status = plugin.status()
    assert status["plugin"] == "layer2_risk_fusion"
    assert status["status"] == "active"
    assert set(status["artifacts"].keys()) == {"unsupervised", "supervised", "stacker"}


def test_layer2_plugin_analyze_batch_contract() -> None:
    plugin = Layer2RiskFusionPlugin(org_id=None)
    result = plugin.analyze_batch(_sample_rows())

    assert result["plugin"] == "layer2_risk_fusion"
    assert result["count"] == 12
    assert 0.0 <= result["summary"]["avg_risk_probability"] <= 1.0
    assert result["summary"]["high_risk_count"] >= 0
    assert len(result["transactions"]) == 12
    first = result["transactions"][0]
    assert set(first["layers"].keys()) == {
        "rules",
        "unsupervised",
        "supervised",
        "temporal",
        "graph",
        "assertions",
    }
    assert 0.0 <= first["risk_probability"] <= 1.0
