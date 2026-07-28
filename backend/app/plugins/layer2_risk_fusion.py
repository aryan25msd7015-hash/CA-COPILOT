"""Layer-2 plugin wrapper for HAE risk fusion and explainability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.engines import model_registry
from app.engines.hybrid_audit_engine import (
    STACKER_MODEL_NAME,
    SUPERVISED_MODEL_NAME,
    UNSUPERVISED_MODEL_NAME,
    score_transactions,
)


@dataclass
class Layer2RiskFusionPlugin:
    org_id: str | None = None

    def status(self) -> dict[str, Any]:
        return {
            "plugin": "layer2_risk_fusion",
            "status": "active",
            "org_id": self.org_id,
            "artifacts": {
                "unsupervised": model_registry.load_artifact(self.org_id, UNSUPERVISED_MODEL_NAME) is not None,
                "supervised": model_registry.load_artifact(self.org_id, SUPERVISED_MODEL_NAME) is not None,
                "stacker": model_registry.load_artifact(self.org_id, STACKER_MODEL_NAME) is not None,
            },
        }

    def analyze_batch(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        scored = score_transactions(rows, org_id=self.org_id)
        records = self._records(scored)
        return {
            "plugin": "layer2_risk_fusion",
            "count": len(records),
            "summary": self._summary(records),
            "transactions": records,
        }

    @staticmethod
    def _records(scored: pd.DataFrame) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for row in scored.to_dict(orient="records"):
            records.append(
                {
                    "id": row["id"],
                    "risk_score": float(row.get("audit_risk_score", 0.0)),
                    "risk_probability": float(row.get("audit_risk_prob", 0.0)),
                    "confidence": float(row.get("audit_confidence", 0.0)),
                    "layers": {
                        "rules": float(row.get("rule_score", 0.0)),
                        "unsupervised": float(row.get("unsup_score", 0.0)),
                        "supervised": float(row.get("sup_score", 0.0)),
                        "temporal": float(row.get("tft_score", 0.0)),
                        "graph": float(row.get("gnn_score", 0.0)),
                        "assertions": float(row.get("assertion_score", 0.0)),
                    },
                    "drivers": row.get("drivers") or [],
                    "rule_flags": row.get("rule_flags") or [],
                    "failed_assertions": row.get("failed_assertions") or [],
                    "evidence": row.get("evidence"),
                }
            )
        return records

    @staticmethod
    def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records:
            return {
                "avg_risk_probability": 0.0,
                "high_risk_count": 0,
                "top_driver_features": [],
            }
        avg_risk = round(
            sum(float(item["risk_probability"]) for item in records) / len(records),
            4,
        )
        high_risk_count = sum(1 for item in records if float(item["risk_probability"]) >= 0.7)
        driver_counts: dict[str, int] = {}
        for item in records:
            for driver in item["drivers"][:3]:
                feature = str(driver.get("feature") or "unknown")
                driver_counts[feature] = driver_counts.get(feature, 0) + 1
        top_driver_features = [
            {"feature": feature, "count": count}
            for feature, count in sorted(driver_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        ]
        return {
            "avg_risk_probability": avg_risk,
            "high_risk_count": high_risk_count,
            "top_driver_features": top_driver_features,
        }


def plugin_for_org(org_id: str | None) -> Layer2RiskFusionPlugin:
    return Layer2RiskFusionPlugin(org_id=org_id)
