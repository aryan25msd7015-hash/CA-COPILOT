"""HAE-4 classical ML + meta-fusion layer.

Layers:
  L1 — deterministic rules (via feature_engineering.rule_layer_scores)
  L2 — IsolationForest + LocalOutlierFactor + supervised LightGBM/XGBoost/GBM
  Meta — LightGBM / GradientBoosting stacker + probability calibration
"""
from __future__ import annotations

import logging
import math
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import (
    GradientBoostingClassifier,
    IsolationForest,
)
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

from app.engines.feature_engineering import (
    FEATURE_COLUMNS,
    build_transaction_features,
    rule_layer_scores,
    transactions_to_frame,
)
from app.engines import model_registry

logger = logging.getLogger(__name__)

SUPERVISED_MODEL_NAME = "hae_supervised_risk"
STACKER_MODEL_NAME = "hae_meta_stacker"
UNSUPERVISED_MODEL_NAME = "hae_unsupervised"


def _try_lightgbm():
    try:
        import lightgbm as lgb

        return lgb
    except Exception:
        return None


def _try_xgboost():
    try:
        import xgboost as xgb

        return xgb
    except Exception:
        return None


def _try_shap():
    try:
        import shap

        return shap
    except Exception:
        return None


def train_isolation_forest(transactions_df: pd.DataFrame):
    """Backward-compatible vendor-stats Isolation Forest (legacy API)."""
    if transactions_df.empty:
        return None, pd.DataFrame()
    stats_df = (
        transactions_df.groupby("vendor_gstin")["amount"]
        .agg(["mean", "std", "count"])
        .fillna(0)
    )
    if len(stats_df) < 2:
        return None, stats_df
    model = IsolationForest(contamination=0.02, random_state=42)
    model.fit(stats_df[["mean", "std", "count"]].astype(float))
    return model, stats_df


def score_transaction(model, stats_df: pd.DataFrame, vendor_gstin: str, amount: float) -> float:
    """Legacy Isolation Forest scorer used by existing tests/tasks."""
    if model is None:
        return 0.5
    selected = stats_df[stats_df.index == vendor_gstin]
    if selected.empty:
        return 0.75
    vendor = selected.iloc[0]
    vendor_std = max(float(vendor["std"]), max(abs(float(vendor["mean"])) * 0.05, 1.0))
    amount_z = abs(float(amount) - float(vendor["mean"])) / vendor_std
    features = pd.DataFrame(
        [[vendor["mean"], vendor["std"], vendor["count"]]],
        columns=["mean", "std", "count"],
    )
    vendor_decision = float(model.decision_function(features)[0])
    vendor_risk = 1.0 / (1.0 + math.exp(8.0 * vendor_decision))
    amount_risk = 1.0 - math.exp(-amount_z / 3.0)
    risk = max(vendor_risk, amount_risk)
    return round(max(0.0, min(1.0, risk)), 4)


def fit_unsupervised(feature_matrix: pd.DataFrame) -> dict[str, Any]:
    """Fit IsolationForest + LOF on tabular HAE features."""
    X = feature_matrix[FEATURE_COLUMNS].astype(float).values
    if len(X) < 2:
        return {"iforest": None, "lof": None, "scaler": None}
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    iforest = IsolationForest(
        n_estimators=200,
        contamination=min(0.05, max(0.01, 2.0 / max(len(X), 1))),
        random_state=42,
    )
    iforest.fit(Xs)
    lof = None
    if len(X) >= 5:
        n_neighbors = min(20, max(2, len(X) // 3))
        lof = LocalOutlierFactor(
            n_neighbors=n_neighbors,
            contamination=min(0.05, max(0.01, 2.0 / max(len(X), 1))),
            novelty=True,
        )
        lof.fit(Xs)
    return {"iforest": iforest, "lof": lof, "scaler": scaler}


def score_unsupervised(bundle: dict[str, Any], feature_matrix: pd.DataFrame) -> np.ndarray:
    n = len(feature_matrix)
    if not bundle or bundle.get("iforest") is None or n == 0:
        return np.full(n, 0.5)
    X = feature_matrix[FEATURE_COLUMNS].astype(float).values
    scaler = bundle.get("scaler")
    Xs = scaler.transform(X) if scaler is not None else X
    if_scores = bundle["iforest"].decision_function(Xs)
    if_risk = 1.0 / (1.0 + np.exp(8.0 * if_scores))
    if bundle.get("lof") is not None:
        try:
            lof_scores = bundle["lof"].decision_function(Xs)
            lof_risk = 1.0 / (1.0 + np.exp(5.0 * lof_scores))
            return np.clip(np.maximum(if_risk, lof_risk), 0.0, 1.0)
        except Exception:
            return np.clip(if_risk, 0.0, 1.0)
    return np.clip(if_risk, 0.0, 1.0)


def _make_supervised_estimator():
    lgb = _try_lightgbm()
    if lgb is not None:
        return lgb.LGBMClassifier(
            n_estimators=120,
            learning_rate=0.05,
            max_depth=5,
            num_leaves=31,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=42,
            verbose=-1,
        )
    xgb = _try_xgboost()
    if xgb is not None:
        return xgb.XGBClassifier(
            n_estimators=120,
            learning_rate=0.05,
            max_depth=5,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="logloss",
            random_state=42,
            verbosity=0,
        )
    return GradientBoostingClassifier(random_state=42)


def fit_supervised(feature_matrix: pd.DataFrame, labels: np.ndarray) -> dict[str, Any] | None:
    """Train supervised risk model when both classes are present."""
    y = np.asarray(labels).astype(int)
    if len(feature_matrix) < 8 or len(np.unique(y)) < 2:
        return None
    X = feature_matrix[FEATURE_COLUMNS].astype(float).values
    base = _make_supervised_estimator()
    try:
        calibrated = CalibratedClassifierCV(base, method="isotonic", cv=min(3, int(y.sum()) or 2))
        calibrated.fit(X, y)
        model = calibrated
    except Exception:
        base.fit(X, y)
        model = base
    return {"model": model, "feature_columns": list(FEATURE_COLUMNS)}


def score_supervised(bundle: dict[str, Any] | None, feature_matrix: pd.DataFrame) -> np.ndarray:
    n = len(feature_matrix)
    if not bundle or bundle.get("model") is None or n == 0:
        return np.full(n, 0.5)
    X = feature_matrix[FEATURE_COLUMNS].astype(float).values
    model = bundle["model"]
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(X)
        # class 1 = risky / confirmed
        if proba.shape[1] == 1:
            return np.clip(proba[:, 0], 0.0, 1.0)
        return np.clip(proba[:, 1], 0.0, 1.0)
    preds = model.predict(X)
    return np.clip(preds.astype(float), 0.0, 1.0)


def fit_stacker(base_scores: pd.DataFrame, labels: np.ndarray) -> dict[str, Any] | None:
    """Meta LightGBM/GBM stacker over layer scores."""
    y = np.asarray(labels).astype(int)
    cols = [c for c in base_scores.columns if c != "id"]
    if len(base_scores) < 8 or len(np.unique(y)) < 2 or not cols:
        return None
    X = base_scores[cols].astype(float).values
    est = _make_supervised_estimator()
    try:
        calibrated = CalibratedClassifierCV(est, method="isotonic", cv=min(3, max(2, int(y.sum()))))
        calibrated.fit(X, y)
        model = calibrated
    except Exception:
        est.fit(X, y)
        model = est
    return {"model": model, "columns": cols}


def score_stacker(bundle: dict[str, Any] | None, base_scores: pd.DataFrame) -> np.ndarray:
    n = len(base_scores)
    cols = [c for c in [
        "rule_score", "unsup_score", "sup_score", "tft_score", "gnn_score", "assertion_score",
    ] if c in base_scores.columns]
    if n == 0:
        return np.array([])
    if not bundle or bundle.get("model") is None:
        # Precision-first fusion: assertions + supervised dominate when present
        weights = {
            "assertion_score": 0.28,
            "rule_score": 0.14,
            "unsup_score": 0.12,
            "sup_score": 0.22,
            "tft_score": 0.12,
            "gnn_score": 0.12,
        }
        total = np.zeros(n)
        wsum = 0.0
        for col, w in weights.items():
            if col in base_scores.columns:
                total += w * base_scores[col].astype(float).values
                wsum += w
        if wsum <= 0:
            return np.full(n, 0.5)
        fused = total / wsum
        # Human-auditor compounding: if assertion and any ML layer both high, escalate
        if "assertion_score" in base_scores.columns:
            a = base_scores["assertion_score"].astype(float).values
            peer = np.maximum.reduce([
                base_scores[c].astype(float).values
                for c in ("rule_score", "unsup_score", "sup_score", "tft_score", "gnn_score")
                if c in base_scores.columns
            ] or [np.zeros(n)])
            boost = np.where((a >= 0.6) & (peer >= 0.55), 0.08, 0.0)
            fused = np.clip(fused + boost, 0.0, 1.0)
        return fused
    use_cols = bundle.get("columns") or cols
    for col in use_cols:
        if col not in base_scores.columns:
            base_scores[col] = 0.5
    X = base_scores[use_cols].astype(float).values
    model = bundle["model"]
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(X)
        return np.clip(proba[:, -1], 0.0, 1.0)
    return np.clip(model.predict(X).astype(float), 0.0, 1.0)


def explain_drivers(
    feature_matrix: pd.DataFrame,
    supervised_bundle: dict[str, Any] | None,
    base_scores: pd.DataFrame,
    fused: np.ndarray,
    top_k: int = 5,
) -> list[list[dict]]:
    """Return top-k human-readable risk drivers per transaction."""
    n = len(feature_matrix)
    drivers: list[list[dict]] = [[] for _ in range(n)]

    # Layer contributions
    layer_cols = [c for c in [
        "rule_score", "unsup_score", "sup_score", "tft_score", "gnn_score", "assertion_score",
    ] if c in base_scores.columns]
    for i in range(n):
        layer_bits = []
        for col in layer_cols:
            val = float(base_scores.iloc[i][col])
            if val >= 0.55:
                layer_bits.append({
                    "feature": col.replace("_score", ""),
                    "contribution": round(val, 4),
                    "direction": "increases_risk",
                })
        drivers[i].extend(sorted(layer_bits, key=lambda d: -d["contribution"])[:3])

    # Feature-level: SHAP if available, else abs z / magnitude heuristics
    shap_mod = _try_shap()
    model = (supervised_bundle or {}).get("model")
    if shap_mod is not None and model is not None and n > 0:
        try:
            X = feature_matrix[FEATURE_COLUMNS].astype(float).values
            # Prefer tree explainer on underlying estimator when calibrated
            est = model
            if hasattr(model, "calibrated_classifiers_"):
                est = model.calibrated_classifiers_[0].estimator
            explainer = shap_mod.Explainer(est.predict if hasattr(est, "predict") else model.predict, X[: min(50, n)])
            sv = explainer(X)
            values = np.asarray(sv.values)
            if values.ndim == 3:
                values = values[:, :, -1]
            for i in range(n):
                idxs = np.argsort(-np.abs(values[i]))[:top_k]
                for j in idxs:
                    drivers[i].append({
                        "feature": FEATURE_COLUMNS[int(j)],
                        "contribution": round(float(values[i][j]), 4),
                        "direction": "increases_risk" if values[i][j] > 0 else "decreases_risk",
                    })
        except Exception as exc:
            logger.debug("SHAP explain failed: %s", exc)

    if not any(drivers):
        # Heuristic fallback
        for i in range(n):
            row = feature_matrix.iloc[i]
            candidates = []
            for col in ("vendor_amount_z", "is_threshold_band", "is_round_1000", "is_weekend", "match_unmatched", "fraud_flagged"):
                val = float(row.get(col, 0) or 0)
                if abs(val) > 0.5:
                    candidates.append({
                        "feature": col,
                        "contribution": round(abs(val), 4),
                        "direction": "increases_risk",
                    })
            drivers[i] = sorted(candidates, key=lambda d: -d["contribution"])[:top_k]

    # Dedupe + trim
    cleaned = []
    for items in drivers:
        seen = set()
        uniq = []
        for item in items:
            key = item["feature"]
            if key in seen:
                continue
            seen.add(key)
            uniq.append(item)
        cleaned.append(uniq[:top_k])
    return cleaned


def labels_from_reviews(db, client_id: str | None = None, org_id: str | None = None) -> dict[str, int]:
    """Map transaction_id -> 1 confirmed risk / 0 false_positive from review history."""
    from app.models.anomaly_flag import AnomalyFlag
    from app.models.transaction import Transaction

    q = db.query(AnomalyFlag).filter(AnomalyFlag.reviewed.is_(True))
    if client_id:
        q = q.filter(AnomalyFlag.client_id == client_id)
    if org_id:
        q = q.filter(AnomalyFlag.org_id == org_id)
    mapping: dict[str, int] = {}
    for flag in q.all():
        if not flag.transaction_id:
            continue
        tid = str(flag.transaction_id)
        status = (flag.review_status or "").strip()
        if status == "confirmed":
            mapping[tid] = 1
        elif status == "false_positive" and tid not in mapping:
            mapping[tid] = 0

    # Fraud queue labels
    tq = db.query(Transaction)
    if client_id:
        tq = tq.filter(Transaction.client_id == client_id)
    if org_id:
        tq = tq.filter(Transaction.org_id == org_id)
    for txn in tq.filter(Transaction.fraud_review_status.in_(["confirmed", "false_positive", "cleared"])).all():
        tid = str(txn.id)
        if txn.fraud_review_status == "confirmed":
            mapping[tid] = 1
        elif txn.fraud_review_status in {"false_positive", "cleared"} and tid not in mapping:
            mapping[tid] = 0
    return mapping


def train_org_models(db, org_id: str, client_id: str | None = None) -> dict:
    """Train unsupervised + supervised + stacker for an org and persist artifacts."""
    from app.models.transaction import Transaction

    q = db.query(Transaction).filter(Transaction.org_id == org_id, Transaction.amount.isnot(None))
    if client_id:
        q = q.filter(Transaction.client_id == client_id)
    txns = q.all()
    frame = transactions_to_frame(txns)
    features = build_transaction_features(frame)
    unsup = fit_unsupervised(features)
    model_registry.save_artifact(org_id, UNSUPERVISED_MODEL_NAME, unsup, {"n_rows": len(features)})

    label_map = labels_from_reviews(db, client_id=client_id, org_id=org_id)
    y = np.array([label_map.get(str(i), -1) for i in features["id"]], dtype=int)
    mask = y >= 0
    supervised = None
    stacker = None
    metrics = {"labeled_rows": int(mask.sum()), "positive": int((y[mask] == 1).sum()) if mask.any() else 0}
    if mask.sum() >= 8 and len(np.unique(y[mask])) >= 2:
        supervised = fit_supervised(features.loc[mask].reset_index(drop=True), y[mask])
        if supervised:
            model_registry.save_artifact(org_id, SUPERVISED_MODEL_NAME, supervised, metrics)
            rules = rule_layer_scores(frame.loc[mask].reset_index(drop=True) if hasattr(frame, "loc") else frame)
            # Align rules to labeled feature ids
            labeled_ids = features.loc[mask, "id"].astype(str).tolist()
            id_to_rule = dict(zip(rules["id"].astype(str), rules["rule_score"]))
            base = pd.DataFrame({
                "id": labeled_ids,
                "rule_score": [id_to_rule.get(i, 0.0) for i in labeled_ids],
                "unsup_score": score_unsupervised(unsup, features.loc[mask].reset_index(drop=True)),
                "sup_score": score_supervised(supervised, features.loc[mask].reset_index(drop=True)),
                "tft_score": np.full(mask.sum(), 0.5),
                "gnn_score": np.full(mask.sum(), 0.5),
                "assertion_score": np.full(mask.sum(), 0.5),
            })
            stacker = fit_stacker(base, y[mask])
            if stacker:
                model_registry.save_artifact(org_id, STACKER_MODEL_NAME, stacker, metrics)

    return {
        "org_id": org_id,
        "n_transactions": len(features),
        "metrics": metrics,
        "supervised": supervised is not None,
        "stacker": stacker is not None,
    }


def score_transactions(
    rows,
    org_id: str | None = None,
    tft_scores: Optional[dict[str, float]] = None,
    gnn_scores: Optional[dict[str, float]] = None,
    assertion_scores: Optional[dict[str, float]] = None,
    assertion_payloads: Optional[dict[str, dict]] = None,
    confidence_scores: Optional[dict[str, float]] = None,
) -> pd.DataFrame:
    """Score transactions with HAE-5 precision fusion. Returns one row per transaction."""
    frame = transactions_to_frame(rows)
    if frame.empty:
        return pd.DataFrame(columns=[
            "id", "rule_score", "unsup_score", "sup_score", "tft_score", "gnn_score",
            "assertion_score", "audit_risk_score", "audit_risk_prob", "audit_confidence",
            "drivers", "rule_flags", "evidence", "failed_assertions",
        ])

    features = build_transaction_features(frame)
    rules = rule_layer_scores(frame)
    unsup = model_registry.load_artifact(org_id, UNSUPERVISED_MODEL_NAME)
    if unsup is None:
        unsup = fit_unsupervised(features)
    supervised = model_registry.load_artifact(org_id, SUPERVISED_MODEL_NAME)
    stacker = model_registry.load_artifact(org_id, STACKER_MODEL_NAME)

    unsup_scores = score_unsupervised(unsup, features)
    sup_scores = score_supervised(supervised, features)
    tft = np.array([float((tft_scores or {}).get(str(i), 0.5)) for i in features["id"]])
    gnn = np.array([float((gnn_scores or {}).get(str(i), 0.5)) for i in features["id"]])
    assertion = np.array([float((assertion_scores or {}).get(str(i), 0.05)) for i in features["id"]])
    confidence = np.array([float((confidence_scores or {}).get(str(i), 0.5)) for i in features["id"]])

    rule_map = dict(zip(rules["id"].astype(str), rules["rule_score"]))
    flag_map = dict(zip(rules["id"].astype(str), rules["rule_flags"]))
    base = pd.DataFrame({
        "id": features["id"].astype(str),
        "rule_score": [float(rule_map.get(str(i), 0.0)) for i in features["id"]],
        "unsup_score": unsup_scores,
        "sup_score": sup_scores,
        "tft_score": tft,
        "gnn_score": gnn,
        "assertion_score": assertion,
    })
    fused = score_stacker(stacker, base)
    # Precision calibration: when evidence is thin, dampen extreme scores slightly
    # (avoid over-confident false positives); when assertions fire hard, keep high.
    calibrated = fused.copy()
    calibrated = np.where(
        (assertion < 0.35) & (confidence < 0.4) & (fused > 0.75),
        fused * 0.9,
        calibrated,
    )
    calibrated = np.where(assertion >= 0.75, np.maximum(calibrated, assertion * 0.95), calibrated)
    calibrated = np.clip(calibrated, 0.0, 1.0)

    drivers = explain_drivers(features, supervised, base, calibrated)
    # Append assertion drivers in auditor language
    payloads = assertion_payloads or {}
    for i, tid in enumerate(features["id"].astype(str).tolist()):
        payload = payloads.get(tid) or {}
        for assertion_name in (payload.get("failed_assertions") or [])[:3]:
            drivers[i].append({
                "feature": f"assertion:{assertion_name}",
                "contribution": float((payload.get("assertions") or {}).get(assertion_name, {}).get("score") or assertion[i]),
                "direction": "increases_risk",
            })
        drivers[i] = drivers[i][:6]

    out = base.copy()
    out["audit_risk_score"] = np.round(calibrated * 100.0, 2)
    out["audit_risk_prob"] = np.round(calibrated, 4)
    out["audit_confidence"] = np.round(confidence, 4)
    out["drivers"] = drivers
    out["rule_flags"] = [flag_map.get(str(i), []) for i in features["id"]]
    out["evidence"] = [(payloads.get(str(i)) or {}).get("evidence") for i in features["id"]]
    out["failed_assertions"] = [(payloads.get(str(i)) or {}).get("failed_assertions") or [] for i in features["id"]]
    return out
