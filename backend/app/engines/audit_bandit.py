"""Contextual bandit for audit review prioritization (HAE Layer 4).

LinUCB over exception / anomaly candidates. Reward = confirmed finding
efficiency (1 for confirmed, 0 for false_positive, 0.4 for needs_followup).
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

import numpy as np

from app.engines import model_registry

logger = logging.getLogger(__name__)

BANDIT_MODEL_NAME = "hae_linucb_bandit"
CONTEXT_DIM = 8
DEFAULT_ALPHA = 0.6


def context_vector(
    risk_prob: float = 0.5,
    impact_amount: float = 0.0,
    age_hours: float = 0.0,
    source_anomaly: float = 0.0,
    source_fraud: float = 0.0,
    source_msme: float = 0.0,
    source_deadline: float = 0.0,
    firm_capacity: float = 1.0,
) -> np.ndarray:
    """Build normalized context features for a review candidate."""
    return np.asarray([
        float(np.clip(risk_prob, 0.0, 1.0)),
        float(np.clip(np.log1p(max(impact_amount, 0.0)) / 15.0, 0.0, 1.0)),
        float(np.clip(age_hours / 168.0, 0.0, 1.0)),  # week-scaled
        float(source_anomaly),
        float(source_fraud),
        float(source_msme),
        float(source_deadline),
        float(np.clip(firm_capacity, 0.0, 1.0)),
    ], dtype=np.float64)


class LinUCBBandit:
    def __init__(self, n_arms: int = 3, dim: int = CONTEXT_DIM, alpha: float = DEFAULT_ALPHA):
        """
        Arms:
          0 — defer / low priority
          1 — standard review queue
          2 — escalate / sample for substantive testing
        """
        self.n_arms = n_arms
        self.dim = dim
        self.alpha = alpha
        self.A = [np.eye(dim) for _ in range(n_arms)]
        self.b = [np.zeros(dim) for _ in range(n_arms)]

    def _theta(self, arm: int) -> np.ndarray:
        return np.linalg.solve(self.A[arm], self.b[arm])

    def select(self, context: np.ndarray) -> tuple[int, float]:
        x = np.asarray(context, dtype=np.float64).reshape(-1)
        best_arm, best_ucb = 0, -1e18
        for arm in range(self.n_arms):
            theta = self._theta(arm)
            invA = np.linalg.inv(self.A[arm])
            ucb = float(theta @ x + self.alpha * np.sqrt(max(x @ invA @ x, 0.0)))
            if ucb > best_ucb:
                best_ucb, best_arm = ucb, arm
        return best_arm, best_ucb

    def update(self, arm: int, context: np.ndarray, reward: float) -> None:
        x = np.asarray(context, dtype=np.float64).reshape(-1)
        self.A[arm] = self.A[arm] + np.outer(x, x)
        self.b[arm] = self.b[arm] + reward * x

    def to_dict(self) -> dict:
        return {
            "n_arms": self.n_arms,
            "dim": self.dim,
            "alpha": self.alpha,
            "A": [a.tolist() for a in self.A],
            "b": [b.tolist() for b in self.b],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LinUCBBandit":
        bandit = cls(
            n_arms=int(data.get("n_arms", 3)),
            dim=int(data.get("dim", CONTEXT_DIM)),
            alpha=float(data.get("alpha", DEFAULT_ALPHA)),
        )
        if data.get("A"):
            bandit.A = [np.asarray(a, dtype=np.float64) for a in data["A"]]
        if data.get("b"):
            bandit.b = [np.asarray(b, dtype=np.float64) for b in data["b"]]
        return bandit


ARM_LABELS = {
    0: "defer",
    1: "standard_review",
    2: "escalate_sample",
}


def load_bandit(org_id: str | None = None) -> LinUCBBandit:
    payload = model_registry.load_artifact(org_id, BANDIT_MODEL_NAME)
    if isinstance(payload, dict) and payload.get("A"):
        return LinUCBBandit.from_dict(payload)
    if isinstance(payload, LinUCBBandit):
        return payload
    return LinUCBBandit()


def save_bandit(bandit: LinUCBBandit, org_id: str | None = None) -> dict:
    return model_registry.save_artifact(org_id, BANDIT_MODEL_NAME, bandit.to_dict(), {
        "n_arms": bandit.n_arms,
        "alpha": bandit.alpha,
    })


def reward_from_review(status: str) -> float:
    status = (status or "").strip().lower()
    if status in {"confirmed", "approved", "resolved"}:
        return 1.0
    if status in {"needs_followup", "in_review"}:
        return 0.4
    if status in {"false_positive", "dismissed", "cleared"}:
        return 0.0
    return 0.2


def prioritize_candidates(
    candidates: Iterable[dict[str, Any]],
    org_id: str | None = None,
    firm_capacity: float = 1.0,
    explore: bool = True,
) -> list[dict[str, Any]]:
    """
    Rank review candidates with LinUCB.

    Each candidate may include:
      risk_prob, impact_amount, age_hours, source_type, id/fingerprint
    """
    bandit = load_bandit(org_id)
    ranked = []
    for raw in candidates:
        source = (raw.get("source_type") or raw.get("flag_type") or "").lower()
        ctx = context_vector(
            risk_prob=float(raw.get("risk_prob") or raw.get("risk_score") or raw.get("audit_risk_prob") or 0.5),
            impact_amount=float(raw.get("impact_amount") or raw.get("amount") or 0.0),
            age_hours=float(raw.get("age_hours") or 0.0),
            source_anomaly=1.0 if "anomaly" in source or source in {
                "isolation_forest", "benford", "vendor_spike", "hybrid_fusion", "round_number",
                "weekend", "duplicate", "threshold_gaming", "temporal", "graph_collusion",
            } else 0.0,
            source_fraud=1.0 if "fraud" in source or source == "invoice_fraud" else 0.0,
            source_msme=1.0 if "msme" in source else 0.0,
            source_deadline=1.0 if "deadline" in source else 0.0,
            firm_capacity=firm_capacity,
        )
        arm, ucb = bandit.select(ctx)
        # Blend UCB with raw risk for stable cold-start ranking
        risk = float(raw.get("risk_prob") or raw.get("risk_score") or raw.get("audit_risk_prob") or 0.5)
        if risk > 1.0:
            risk = risk / 100.0
        priority = 0.55 * risk + 0.45 * (1.0 / (1.0 + np.exp(-ucb)))
        if not explore and arm == 0 and risk < 0.7:
            priority *= 0.5
        item = dict(raw)
        item["bandit_arm"] = int(arm)
        item["bandit_arm_label"] = ARM_LABELS.get(arm, "standard_review")
        item["bandit_ucb"] = round(float(ucb), 4)
        item["priority_score"] = round(float(priority), 4)
        item["bandit_context"] = ctx.tolist()
        ranked.append(item)
    ranked.sort(key=lambda r: (-r["priority_score"], -float(r.get("impact_amount") or 0)))
    return ranked


def record_bandit_feedback(
    org_id: str,
    context: list[float] | np.ndarray,
    arm: int,
    review_status: str,
) -> dict:
    bandit = load_bandit(org_id)
    reward = reward_from_review(review_status)
    bandit.update(int(arm), np.asarray(context, dtype=np.float64), reward)
    meta = save_bandit(bandit, org_id)
    return {"reward": reward, "arm": int(arm), "artifact": meta}


def adaptive_sample_plan(
    scored_transactions: list[dict[str, Any]],
    materiality: float = 100000.0,
    review_budget: int = 25,
    org_id: str | None = None,
    performance_materiality: float | None = None,
    clearly_trivial: float | None = None,
) -> dict[str, Any]:
    """
    Auditor-fluent substantive sample:
      1) 100% of items >= performance materiality
      2) Monetary-unit / risk-weighted selection of remaining population
      3) Strata coverage (high/med/low risk) so low-risk mass is not ignored
      4) Report population coverage % and residual unsampled high-risk
    """
    pm = float(performance_materiality or (materiality * 0.75))
    trivial = float(clearly_trivial or (pm * 0.05))

    candidates = []
    for row in scored_transactions:
        risk = float(row.get("audit_risk_prob") or row.get("risk_prob") or 0)
        if risk > 1:
            risk = risk / 100.0
        amount = abs(float(row.get("amount") or row.get("impact_amount") or 0))
        candidates.append({
            **row,
            "risk_prob": risk,
            "impact_amount": amount,
            "source_type": row.get("source_type") or "anomaly",
            "stratum": (
                "material" if amount >= pm else
                "high_risk" if risk >= 0.65 else
                "medium_risk" if risk >= 0.4 else
                "low_risk"
            ),
        })

    population_amount = sum(c["impact_amount"] for c in candidates) or 1.0
    population_count = len(candidates)

    # Mandatory: all material items
    selected_ids: set[str] = set()
    selected: list[dict[str, Any]] = []
    for item in sorted(candidates, key=lambda r: -r["impact_amount"]):
        tid = str(item.get("id") or item.get("transaction_id"))
        if item["impact_amount"] >= pm and tid not in selected_ids:
            selected.append({**item, "selection_reason": "performance_materiality"})
            selected_ids.add(tid)

    # Bandit rank the rest
    remaining = [c for c in candidates if str(c.get("id") or c.get("transaction_id")) not in selected_ids]
    ranked = prioritize_candidates(remaining, org_id=org_id, explore=True)

    # MUS-like weight: amount * (0.35 + 0.65*risk)
    def mus_weight(item: dict) -> float:
        return float(item["impact_amount"]) * (0.35 + 0.65 * float(item.get("risk_prob") or 0))

    ranked.sort(key=lambda r: (-mus_weight(r), -float(r.get("priority_score") or 0)))

    # Ensure each stratum gets at least a slice of remaining budget
    budget_left = max(0, review_budget - len(selected))
    stratum_quota = {
        "high_risk": max(1, budget_left // 2),
        "medium_risk": max(1, budget_left // 4),
        "low_risk": max(1, budget_left // 8),
        "material": 0,
    }
    stratum_taken = {k: 0 for k in stratum_quota}

    for item in ranked:
        if len(selected) >= review_budget:
            break
        tid = str(item.get("id") or item.get("transaction_id"))
        if tid in selected_ids:
            continue
        if item["impact_amount"] < trivial and item.get("risk_prob", 0) < 0.45:
            continue
        stratum = item.get("stratum") or "low_risk"
        # Prefer filling quotas first
        if stratum_taken.get(stratum, 0) >= stratum_quota.get(stratum, 0) and len(selected) > review_budget * 0.7:
            # still allow exceptional high MUS weight
            if mus_weight(item) < pm * 0.2:
                continue
        selected.append({**item, "selection_reason": f"mus_risk:{stratum}"})
        selected_ids.add(tid)
        stratum_taken[stratum] = stratum_taken.get(stratum, 0) + 1

    covered = sum(float(s.get("impact_amount") or 0) for s in selected)
    high_risk_pop = [c for c in candidates if c["risk_prob"] >= 0.65]
    high_risk_unsampled = [
        c for c in high_risk_pop
        if str(c.get("id") or c.get("transaction_id")) not in selected_ids
    ]

    by_stratum: dict[str, int] = {}
    for s in selected:
        key = s.get("stratum") or "unknown"
        by_stratum[key] = by_stratum.get(key, 0) + 1

    return {
        "materiality": materiality,
        "performance_materiality": pm,
        "clearly_trivial": trivial,
        "review_budget": review_budget,
        "selected_count": len(selected),
        "coverage_amount": round(covered, 2),
        "coverage_ratio": round(covered / max(materiality, 1.0), 4),
        "population_coverage_pct": round(100.0 * covered / population_amount, 2),
        "population_count": population_count,
        "population_amount": round(population_amount, 2),
        "stratum_counts": by_stratum,
        "residual_high_risk_count": len(high_risk_unsampled),
        "residual_high_risk_amount": round(sum(c["impact_amount"] for c in high_risk_unsampled), 2),
        "sample": [
            {
                "id": s.get("id") or s.get("transaction_id"),
                "priority_score": s.get("priority_score"),
                "bandit_arm_label": s.get("bandit_arm_label"),
                "risk_prob": s.get("risk_prob"),
                "impact_amount": s.get("impact_amount"),
                "drivers": s.get("drivers"),
                "stratum": s.get("stratum"),
                "selection_reason": s.get("selection_reason"),
                "failed_assertions": s.get("failed_assertions"),
                "evidence": s.get("evidence"),
            }
            for s in selected
        ],
    }
