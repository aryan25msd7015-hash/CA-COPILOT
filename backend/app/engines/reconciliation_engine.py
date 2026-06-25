"""
GST / ITC three-tier reconciliation engine.

Tier 1: Exact match   — vendor_gstin + invoice_no + amount (confidence 100)
Tier 2: Tolerance     — vendor_gstin exact, amount ±tol, date ±days (confidence 90)
Tier 3: Fuzzy         — token_sort_ratio on vendor_name ≥ threshold, amount ±tol (confidence = fuzz score)
"""
import re
import logging

import pandas as pd
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

_SUFFIX_RE = re.compile(
    r'\b(PVT\.?|LTD\.?|PRIVATE|LIMITED|LLP|CORP\.?|INC\.?)\b',
    flags=re.IGNORECASE,
)


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Pre-pass normalisation — run before any matching tier."""
    df = df.copy()

    if "invoice_no" in df.columns:
        df["invoice_no"] = (
            df["invoice_no"].astype(str).str.upper()
            .str.replace(r'[^A-Z0-9/\-]', '', regex=True)
        )

    if "vendor_name" in df.columns:
        df["vendor_name"] = (
            df["vendor_name"].astype(str).str.upper().str.strip()
        )
        df["vendor_name"] = df["vendor_name"].str.replace(
            _SUFFIX_RE, '', regex=True
        ).str.replace(r'\s+', ' ', regex=True).str.strip()

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")

    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").round(2)

    return df


def reconcile(
    purchase_df: pd.DataFrame,
    gstr2b_df: pd.DataFrame,
    config: dict | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run 3-tier reconciliation.

    Parameters
    ----------
    purchase_df : normalised purchase register DataFrame (must have 'id' column)
    gstr2b_df   : normalised GSTR-2B DataFrame (must have 'id' column)
    config      : dict with keys amount_tolerance, date_tolerance, fuzzy_threshold

    Returns
    -------
    matched_df   : DataFrame with match_type and confidence columns
    unmatched_df : purchase rows with no match
    """
    if config is None:
        config = {}

    amt_tol  = float(config.get("amount_tolerance", 5))
    day_tol  = int(config.get("date_tolerance", 3))
    fuzz_thr = int(config.get("fuzzy_threshold", 85))

    purchase_df = normalize(purchase_df.copy())
    gstr2b_df   = normalize(gstr2b_df.copy())

    results: list[dict] = []
    matched_p: set = set()
    matched_g: set = set()

    # ── Tier 1: Exact ────────────────────────────────────────────────────────
    for _, p in purchase_df.iterrows():
        mask = (
            (gstr2b_df["vendor_gstin"] == p.get("vendor_gstin")) &
            (gstr2b_df["invoice_no"]   == p.get("invoice_no")) &
            (gstr2b_df["amount"]       == p.get("amount")) &
            (~gstr2b_df["id"].isin(matched_g))
        )
        matches = gstr2b_df[mask]
        if not matches.empty:
            g = matches.iloc[0]
            row = p.to_dict()
            row.update({"match_type": "exact", "confidence": 100.0, "g_id": g["id"]})
            results.append(row)
            matched_p.add(p["id"])
            matched_g.add(g["id"])

    # ── Tier 2: Tolerance ────────────────────────────────────────────────────
    rem_p = purchase_df[~purchase_df["id"].isin(matched_p)]
    rem_g = gstr2b_df[~gstr2b_df["id"].isin(matched_g)]

    for _, p in rem_p.iterrows():
        p_date = p.get("date")
        mask = (~rem_g["id"].isin(matched_g)) & \
               (rem_g["vendor_gstin"] == p.get("vendor_gstin")) & \
               (abs(rem_g["amount"] - p.get("amount", 0)) <= amt_tol)
        if p_date is not pd.NaT and pd.notna(p_date):
            date_diff = abs((rem_g["date"] - p_date).dt.days)
            mask = mask & (date_diff <= day_tol)
        matches = rem_g[mask]
        if not matches.empty:
            g = matches.iloc[0]
            row = p.to_dict()
            row.update({"match_type": "tolerance", "confidence": 90.0, "g_id": g["id"]})
            results.append(row)
            matched_p.add(p["id"])
            matched_g.add(g["id"])

    # ── Tier 3: Fuzzy ────────────────────────────────────────────────────────
    rem_p2 = purchase_df[~purchase_df["id"].isin(matched_p)]
    rem_g2 = gstr2b_df[~gstr2b_df["id"].isin(matched_g)]

    for _, p in rem_p2.iterrows():
        p_name = str(p.get("vendor_name", ""))
        best_score, best_g_row = 0, None

        for _, g in rem_g2.iterrows():
            if g["id"] in matched_g:
                continue
            score = fuzz.token_sort_ratio(p_name, str(g.get("vendor_name", "")))
            if score > best_score:
                best_score, best_g_row = score, g

        if (best_g_row is not None and
                best_score >= fuzz_thr and
                abs(p.get("amount", 0) - best_g_row.get("amount", 0)) <= amt_tol):
            row = p.to_dict()
            row.update({
                "match_type": "fuzzy",
                "confidence": float(best_score),
                "g_id": best_g_row["id"],
            })
            results.append(row)
            matched_p.add(p["id"])
            matched_g.add(best_g_row["id"])

    matched_df   = pd.DataFrame(results) if results else pd.DataFrame()
    unmatched_df = purchase_df[~purchase_df["id"].isin(matched_p)].copy()

    return matched_df, unmatched_df
