"""Feature engineering for Hybrid Audit Engine (HAE-4)."""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "amount",
    "tax_amount",
    "tax_ratio",
    "log_amount",
    "day_of_week",
    "day_of_month",
    "is_weekend",
    "is_round_1000",
    "is_threshold_band",
    "match_unmatched",
    "match_exact",
    "match_tolerance",
    "match_fuzzy",
    "vendor_txn_count",
    "vendor_mean",
    "vendor_std",
    "vendor_amount_z",
    "vendor_share",
    "has_gstin",
    "gstin_state_code",
    "fraud_flagged",
    "anomaly_score_prior",
]


MATCH_ONEHOT = {
    "unmatched": "match_unmatched",
    "exact": "match_exact",
    "tolerance": "match_tolerance",
    "fuzzy": "match_fuzzy",
}


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def transactions_to_frame(rows: Iterable) -> pd.DataFrame:
    """Normalize ORM rows or dicts into a feature-ready DataFrame."""
    records = []
    for row in rows:
        if isinstance(row, dict):
            records.append(row)
            continue
        records.append({
            "id": str(getattr(row, "id", "")),
            "org_id": str(getattr(row, "org_id", "") or ""),
            "client_id": str(getattr(row, "client_id", "") or ""),
            "vendor_gstin": getattr(row, "vendor_gstin", None) or "",
            "vendor_name": getattr(row, "vendor_name", None) or "",
            "invoice_no": getattr(row, "invoice_no", None) or "",
            "amount": _safe_float(getattr(row, "amount", 0)),
            "tax_amount": _safe_float(getattr(row, "tax_amount", 0)),
            "date": getattr(row, "date", None),
            "match_status": getattr(row, "match_status", None) or "unmatched",
            "match_confidence": _safe_float(getattr(row, "match_confidence", 0)),
            "anomaly_score": _safe_float(getattr(row, "anomaly_score", 0)),
            "fraud_flag": getattr(row, "fraud_flag", None),
            "fingerprint": getattr(row, "fingerprint", None) or "",
        })
    if not records:
        return pd.DataFrame(columns=["id", "vendor_gstin", "amount", "date"])
    return pd.DataFrame(records)


def build_transaction_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build the HAE tabular feature matrix from normalized transactions."""
    if df is None or df.empty:
        empty = pd.DataFrame(columns=["id", *FEATURE_COLUMNS])
        return empty

    out = df.copy()
    out["amount"] = pd.to_numeric(out.get("amount", 0), errors="coerce").fillna(0.0)
    out["tax_amount"] = pd.to_numeric(out.get("tax_amount", 0), errors="coerce").fillna(0.0)
    out["anomaly_score_prior"] = pd.to_numeric(
        out.get("anomaly_score", 0), errors="coerce"
    ).fillna(0.0)
    out["tax_ratio"] = np.where(
        out["amount"].abs() > 1e-6,
        out["tax_amount"] / out["amount"].abs(),
        0.0,
    )
    out["log_amount"] = np.log1p(out["amount"].abs())

    dates = pd.to_datetime(out.get("date"), errors="coerce")
    out["day_of_week"] = dates.dt.dayofweek.fillna(0).astype(float)
    out["day_of_month"] = dates.dt.day.fillna(1).astype(float)
    out["is_weekend"] = (out["day_of_week"] >= 5).astype(float)
    out["is_round_1000"] = (
        (out["amount"] % 1000 == 0) & (out["amount"] > 10000)
    ).astype(float)
    out["is_threshold_band"] = (
        (out["amount"] >= 45000) & (out["amount"] < 50000)
    ).astype(float)

    match = out.get("match_status", pd.Series(["unmatched"] * len(out))).fillna("unmatched")
    for status, col in MATCH_ONEHOT.items():
        out[col] = (match == status).astype(float)

    vendor = out.get("vendor_gstin", pd.Series([""] * len(out))).fillna("")
    stats = (
        out.assign(vendor_gstin=vendor)
        .groupby("vendor_gstin")["amount"]
        .agg(vendor_txn_count="count", vendor_mean="mean", vendor_std="std")
        .fillna(0)
    )
    out = out.join(stats, on="vendor_gstin")
    out["vendor_txn_count"] = out["vendor_txn_count"].fillna(1.0)
    out["vendor_mean"] = out["vendor_mean"].fillna(out["amount"])
    out["vendor_std"] = out["vendor_std"].fillna(0.0)
    floor = out["vendor_mean"].abs() * 0.05 + 1.0
    out["vendor_std"] = np.where(out["vendor_std"] <= 0, floor, out["vendor_std"])
    out["vendor_amount_z"] = (out["amount"] - out["vendor_mean"]) / out["vendor_std"]
    total = max(float(out["amount"].abs().sum()), 1.0)
    vendor_totals = out.groupby(vendor)["amount"].transform(lambda s: s.abs().sum())
    out["vendor_share"] = vendor_totals / total

    out["has_gstin"] = (vendor.astype(str).str.len() >= 15).astype(float)
    out["gstin_state_code"] = (
        vendor.astype(str).str[:2].apply(
            lambda x: float(x) if str(x).isdigit() else 0.0
        )
    )
    fraud = out.get("fraud_flag")
    if fraud is None:
        out["fraud_flagged"] = 0.0
    else:
        flagged = fraud.notna() & (fraud.astype(str).str.len() > 0) & (fraud.astype(str) != "None")
        out["fraud_flagged"] = flagged.astype(float)

    for col in FEATURE_COLUMNS:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    if "id" not in out.columns:
        out["id"] = [str(i) for i in range(len(out))]

    return out[["id", *FEATURE_COLUMNS]].copy()


def rule_layer_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Deterministic L1 rule scores aligned to transaction ids."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["id", "rule_score", "rule_flags"])

    work = df.copy()
    amount = pd.to_numeric(work.get("amount", 0), errors="coerce").fillna(0.0)
    dates = pd.to_datetime(work.get("date"), errors="coerce")
    flags = []
    scores = []
    for idx in range(len(work)):
        row_flags = []
        score = 0.0
        amt = float(amount.iloc[idx])
        if amt > 10000 and amt % 1000 == 0:
            row_flags.append("round_number")
            score += 0.35
        if dates.iloc[idx] is not pd.NaT and getattr(dates.iloc[idx], "dayofweek", 0) >= 5:
            row_flags.append("weekend")
            score += 0.25
        if 45000 <= amt < 50000:
            row_flags.append("threshold_gaming")
            score += 0.55
        scores.append(min(1.0, score))
        flags.append(row_flags)

    # Duplicates boost
    if "invoice_no" in work.columns and "vendor_gstin" in work.columns:
        dup = work.duplicated(subset=["invoice_no", "vendor_gstin"], keep=False)
        for i, is_dup in enumerate(dup.tolist()):
            if is_dup and work.iloc[i].get("invoice_no"):
                flags[i].append("duplicate")
                scores[i] = min(1.0, scores[i] + 0.85)

    ids = work["id"].astype(str) if "id" in work.columns else pd.Series([str(i) for i in range(len(work))])
    return pd.DataFrame({"id": ids, "rule_score": scores, "rule_flags": flags})
