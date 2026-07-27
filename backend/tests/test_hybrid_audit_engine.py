"""Tests for Hybrid Audit Engine (HAE-4) layers."""
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.engines.anomaly_detector import train_isolation_forest, train_local_outlier_factor, score_transaction
from app.engines.audit_bandit import (
    LinUCBBandit,
    adaptive_sample_plan,
    prioritize_candidates,
    record_bandit_feedback,
    reward_from_review,
)
from app.engines.feature_engineering import build_transaction_features, rule_layer_scores, transactions_to_frame
from app.engines.graph_fraud_engine import build_vendor_graph, score_graph
from app.engines.hybrid_audit_engine import fit_unsupervised, score_transactions, score_unsupervised
from app.engines.temporal_transformer_engine import build_vendor_sequences, score_sequences


def _sample_rows(n: int = 24):
    rows = []
    for i in range(n):
        rows.append({
            "id": f"t{i}",
            "org_id": "org1",
            "client_id": "c1" if i % 2 == 0 else "c2",
            "vendor_gstin": f"27AAAAA{i % 5:04d}A1Z5",
            "vendor_name": f"Vendor {i % 5}",
            "invoice_no": f"INV-{i}",
            "amount": 1000 + i * 50 if i < n - 2 else 47500,
            "tax_amount": 180,
            "date": date.today() - timedelta(days=n - i),
            "match_status": "unmatched" if i % 4 == 0 else "exact",
            "anomaly_score": 0.1,
            "fraud_flag": "bad gstin" if i == n - 1 else None,
        })
    # Force a duplicate pair
    rows[-3]["invoice_no"] = rows[-4]["invoice_no"]
    rows[-3]["vendor_gstin"] = rows[-4]["vendor_gstin"]
    return rows


def test_feature_engineering_builds_columns():
    frame = transactions_to_frame(_sample_rows())
    feats = build_transaction_features(frame)
    assert not feats.empty
    assert "vendor_amount_z" in feats.columns
    assert "is_threshold_band" in feats.columns
    rules = rule_layer_scores(frame)
    assert "rule_score" in rules.columns
    assert any("duplicate" in flags for flags in rules["rule_flags"])


def test_unsupervised_and_fusion_scores():
    rows = _sample_rows()
    scored = score_transactions(rows, org_id=None)
    assert len(scored) == len(rows)
    assert scored["audit_risk_score"].between(0, 100).all()
    assert scored["audit_risk_prob"].between(0, 1).all()
    assert "drivers" in scored.columns
    # Threshold-band / duplicate rows should tend higher than tiny invoices
    high = scored.loc[scored["id"].isin(["t22", "t23"]), "audit_risk_prob"].mean()
    low = scored.loc[scored["id"].isin(["t0", "t1"]), "audit_risk_prob"].mean()
    assert high >= low


def test_lof_and_isolation_forest_still_work():
    frame = pd.DataFrame([
        {"vendor_gstin": f"GSTIN{i}", "amount": amount}
        for i, amount in enumerate([100, 105, 110, 115, 120, 10000, 101, 102, 103, 104])
    ])
    model, stats = train_isolation_forest(frame)
    lof, lof_stats = train_local_outlier_factor(frame)
    assert model is not None
    assert lof is not None
    assert score_transaction(model, stats, "UNKNOWN", 100) == 0.75


def test_temporal_sequence_scores():
    rows = _sample_rows(30)
    X, ids, vendors = build_vendor_sequences(transactions_to_frame(rows))
    assert len(ids) == 30
    assert X.shape[0] == 30
    scores = score_sequences(rows, org_id=None)
    assert len(scores) == 30
    assert all(0.0 <= v <= 1.0 for v in scores.values())


def test_graph_collusion_scores():
    rows = _sample_rows(20)
    graph = build_vendor_graph(transactions_to_frame(rows))
    assert len(graph["vendor_ids"]) >= 1
    scores = score_graph(rows, org_id=None)
    assert scores
    assert all(0.0 <= v <= 1.0 for v in scores.values())


def test_linucb_prioritization_and_feedback(tmp_path, monkeypatch):
    monkeypatch.setenv("HAE_ARTIFACT_DIR", str(tmp_path))
    # Reload registry path via env already read at import — set path through module
    import app.engines.model_registry as registry
    monkeypatch.setattr(registry, "DEFAULT_ARTIFACT_DIR", tmp_path)

    candidates = [
        {"id": "a", "risk_prob": 0.9, "impact_amount": 50000, "source_type": "anomaly", "flag_type": "hybrid_fusion"},
        {"id": "b", "risk_prob": 0.2, "impact_amount": 1000, "source_type": "deadline"},
        {"id": "c", "risk_prob": 0.7, "impact_amount": 20000, "source_type": "fraud"},
    ]
    ranked = prioritize_candidates(candidates, org_id="org-test")
    assert ranked[0]["id"] in {"a", "c"}
    assert "priority_score" in ranked[0]
    assert "bandit_arm_label" in ranked[0]

    bandit = LinUCBBandit()
    ctx = ranked[0]["bandit_context"]
    result = record_bandit_feedback("org-test", ctx, ranked[0]["bandit_arm"], "confirmed")
    assert result["reward"] == 1.0
    assert reward_from_review("false_positive") == 0.0


def test_adaptive_sample_plan():
    scored = [
        {"id": f"t{i}", "amount": 10000 + i * 1000, "audit_risk_prob": 0.1 + (i * 0.05)}
        for i in range(20)
    ]
    plan = adaptive_sample_plan(scored, materiality=50000, review_budget=5, org_id=None)
    assert plan["selected_count"] <= 5
    assert plan["selected_count"] > 0
    assert "sample" in plan


def test_fit_unsupervised_bundle():
    feats = build_transaction_features(transactions_to_frame(_sample_rows()))
    bundle = fit_unsupervised(feats)
    scores = score_unsupervised(bundle, feats)
    assert len(scores) == len(feats)
    assert np.all((scores >= 0) & (scores <= 1))
