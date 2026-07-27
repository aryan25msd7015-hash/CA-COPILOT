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
    "match_confidence_norm",
    "vendor_txn_count",
    "vendor_mean",
    "vendor_std",
    "vendor_amount_z",
    "vendor_share",
    "has_gstin",
    "gstin_state_code",
    "fraud_flagged",
    "anomaly_score_prior",
    "near_period_end",
    "missing_invoice_no",
    "missing_fingerprint",
    "amount_to_population",
    "same_day_same_amount_cluster",
    "has_po_meta",
    "has_grn_meta",
    "related_party_meta",
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
            rec = dict(row)
            rec["id"] = str(rec.get("id", ""))
            if "audit_meta" not in rec or rec["audit_meta"] is None:
                rec["audit_meta"] = {}
            records.append(rec)
            continue
        meta = getattr(row, "audit_meta", None) or {}
        if not isinstance(meta, dict):
            meta = {}
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
            "audit_meta": meta,
        })
    if not records:
        return pd.DataFrame(columns=["id", "vendor_gstin", "amount", "date", "audit_meta"])
    return pd.DataFrame(records)


def build_transaction_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build the HAE tabular feature matrix from normalized transactions."""
    if df is None or df.empty:
        empty = pd.DataFrame(columns=["id", *FEATURE_COLUMNS])
        return empty

    out = df.copy()
    n = len(out)

    def _num_col(name, default=0.0):
        if name in out.columns:
            return pd.to_numeric(out[name], errors="coerce").fillna(default)
        return pd.Series([default] * n, index=out.index)

    out["amount"] = _num_col("amount")
    out["tax_amount"] = _num_col("tax_amount")
    out["anomaly_score_prior"] = _num_col("anomaly_score")
    out["tax_ratio"] = np.where(
        out["amount"].abs() > 1e-6,
        out["tax_amount"] / out["amount"].abs(),
        0.0,
    )
    out["log_amount"] = np.log1p(out["amount"].abs())

    dates = pd.to_datetime(out["date"] if "date" in out.columns else None, errors="coerce")
    if not isinstance(dates, pd.Series):
        dates = pd.Series([pd.NaT] * n, index=out.index)
    out["day_of_week"] = dates.dt.dayofweek.fillna(0).astype(float)
    out["day_of_month"] = dates.dt.day.fillna(1).astype(float)
    out["is_weekend"] = (out["day_of_week"] >= 5).astype(float)
    out["is_round_1000"] = (
        (out["amount"] % 1000 == 0) & (out["amount"] > 10000)
    ).astype(float)
    out["is_threshold_band"] = (
        (out["amount"] >= 45000) & (out["amount"] < 50000)
    ).astype(float)

    match = out["match_status"] if "match_status" in out.columns else pd.Series(["unmatched"] * n, index=out.index)
    match = match.fillna("unmatched")
    for status, col in MATCH_ONEHOT.items():
        out[col] = (match == status).astype(float)

    vendor = out["vendor_gstin"] if "vendor_gstin" in out.columns else pd.Series([""] * n, index=out.index)
    vendor = vendor.fillna("")
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
    if "fraud_flag" in out.columns:
        fraud = out["fraud_flag"]
        flagged = fraud.notna() & (fraud.astype(str).str.len() > 0) & (fraud.astype(str) != "None")
        out["fraud_flagged"] = flagged.astype(float)
    else:
        out["fraud_flagged"] = 0.0

    # Precision / auditor-style features from transaction log + optional audit_meta
    conf = _num_col("match_confidence")
    out["match_confidence_norm"] = (conf / 100.0).clip(0.0, 1.0)
    invoice_series = out["invoice_no"] if "invoice_no" in out.columns else pd.Series([""] * n, index=out.index)
    fingerprint_series = out["fingerprint"] if "fingerprint" in out.columns else pd.Series([""] * n, index=out.index)
    out["missing_invoice_no"] = (invoice_series.fillna("").astype(str).str.strip() == "").astype(float)
    out["missing_fingerprint"] = (fingerprint_series.fillna("").astype(str).str.strip() == "").astype(float)
    pop = max(float(out["amount"].abs().sum()), 1.0)
    out["amount_to_population"] = out["amount"].abs() / pop

    month = dates.dt.month.fillna(0)
    day = dates.dt.day.fillna(0)
    out["near_period_end"] = (
        ((month == 3) & (day >= 24)) | ((day >= 28) & (month.isin([3, 6, 9, 12])))
    ).astype(float)

    day_key = dates.dt.strftime("%Y-%m-%d").fillna("")
    amt_key = out["amount"].abs().round(0)
    cluster = out.assign(_day=day_key, _amt=amt_key, vendor_gstin=vendor).groupby(
        ["vendor_gstin", "_day", "_amt"]
    )["amount"].transform("count")
    out["same_day_same_amount_cluster"] = pd.to_numeric(cluster, errors="coerce").fillna(1.0).clip(0, 20) / 20.0

    metas = out["audit_meta"] if "audit_meta" in out.columns else pd.Series([{}] * n, index=out.index)

    def _meta_flag(series, key):
        flags = []
        for item in series.tolist():
            meta = item if isinstance(item, dict) else {}
            val = meta.get(key)
            flags.append(1.0 if val not in (None, "", False, 0, "0", "false") else 0.0)
        return np.asarray(flags, dtype=float)

    out["has_po_meta"] = _meta_flag(metas, "po_number")
    out["has_grn_meta"] = _meta_flag(metas, "grn_number")
    out["related_party_meta"] = _meta_flag(metas, "related_party")

    for col in FEATURE_COLUMNS:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    if "id" not in out.columns:
        out["id"] = [str(i) for i in range(n)]

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
