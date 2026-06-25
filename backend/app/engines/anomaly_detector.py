"""Isolation Forest anomaly detection and rule-based flags."""
import math

import pandas as pd
from sklearn.ensemble import IsolationForest

BENFORD = [0.301, 0.176, 0.125, 0.097, 0.079, 0.067, 0.058, 0.051, 0.046]


def train_isolation_forest(transactions_df: pd.DataFrame):
    """Fit a deterministic Isolation Forest on vendor-level statistics."""
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
    """Return an anomaly risk score from 0 to 1."""
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


def benford_test(amounts: list) -> dict:
    """Chi-square Benford test with a Wilson-Hilferty p-value approximation."""
    valid = [a for a in amounts if a and a != 0]
    if len(valid) < 10:
        return {"chi2": 0.0, "p_value": 1.0, "suspicious": False, "note": "insufficient data"}
    first_digits = [int(str(abs(a))[0]) for a in valid]
    observed_counts = [first_digits.count(d) for d in range(1, 10)]
    expected_counts = [p * len(first_digits) for p in BENFORD]
    observed = [count / len(first_digits) for count in observed_counts]
    chi2 = sum((o - e) ** 2 / e for o, e in zip(observed_counts, expected_counts))
    degrees = 8
    z = ((chi2 / degrees) ** (1 / 3) - (1 - 2 / (9 * degrees))) / math.sqrt(2 / (9 * degrees))
    p_value = 0.5 * math.erfc(z / math.sqrt(2))
    return {
        "chi2": round(chi2, 3),
        "p_value": round(p_value, 4),
        "suspicious": p_value < 0.05,
        "deviation": [round(o - e, 3) for o, e in zip(observed, BENFORD)],
    }


def flag_rule_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["flag_round"] = (df["amount"] % 1000 == 0) & (df["amount"] > 10000)
    df["flag_weekend"] = (
        pd.to_datetime(df["date"], errors="coerce").dt.dayofweek >= 5
        if "date" in df.columns else False
    )
    df["flag_duplicate"] = df.duplicated(subset=["invoice_no", "vendor_gstin"], keep=False)
    df["flag_threshold"] = (df["amount"] >= 45000) & (df["amount"] < 50000)
    df["risk_flags"] = (
        df["flag_round"].astype(int) +
        df["flag_weekend"].astype(int) +
        df["flag_duplicate"].astype(int) * 3 +
        df["flag_threshold"].astype(int) * 2
    )
    return df


def detect_vendor_spikes(client_id: str, db) -> list[dict]:
    from datetime import date, timedelta
    from app.models.transaction import Transaction

    today = date.today()
    three_months_ago = today - timedelta(days=90)
    six_months_ago = today - timedelta(days=180)
    recent = db.query(Transaction).filter(
        Transaction.client_id == client_id, Transaction.date >= three_months_ago
    ).all()
    prior = db.query(Transaction).filter(
        Transaction.client_id == client_id,
        Transaction.date >= six_months_ago,
        Transaction.date < three_months_ago,
    ).all()
    recent_df = pd.DataFrame([{"vendor_gstin": r.vendor_gstin, "amount": float(r.amount or 0)} for r in recent])
    prior_df = pd.DataFrame([{"vendor_gstin": r.vendor_gstin, "amount": float(r.amount or 0)} for r in prior])
    if recent_df.empty:
        return []
    spikes = []
    for gstin in recent_df["vendor_gstin"].dropna().unique():
        current_total = float(recent_df[recent_df["vendor_gstin"] == gstin]["amount"].sum())
        prior_total = 0.0 if prior_df.empty else float(prior_df[prior_df["vendor_gstin"] == gstin]["amount"].sum())
        prior_monthly = prior_total / 3
        if prior_monthly > 0 and current_total > prior_monthly * 3:
            spikes.append({
                "vendor_gstin": gstin,
                "current_3m": current_total,
                "prior_monthly_avg": prior_monthly,
                "multiple": round(current_total / prior_monthly, 1),
            })
    return sorted(spikes, key=lambda row: -row["multiple"])
