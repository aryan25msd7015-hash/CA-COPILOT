"""Human-auditor assertion engine for precise transaction-log auditing.

Implements SA/ICAI-style procedures that a fluent engagement team would run:
  - Planning materiality / performance materiality
  - Cut-off (period-end window)
  - Completeness & existence proxies from books vs GST match
  - Classification / tax arithmetic reasonableness
  - Related-party / circular-trading proxies
  - Journal-entry style tests on the voucher population
  - Three-way / GST match assertion
  - Aging / stale open items
  - Population coverage diagnostics

Works with current Transaction fields and optional ``audit_meta`` enrichment
(account_code, je_id, po_number, grn_number, due_date, related_party, period_end).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

from app.engines.feature_engineering import transactions_to_frame


ASSERTION_TYPES = (
    "cutoff",
    "completeness",
    "existence",
    "classification",
    "related_party",
    "journal_entry",
    "three_way_match",
    "aging",
    "accuracy",
)


def _as_date(value) -> Optional[date]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def infer_period_end(dates: Iterable, explicit: date | None = None) -> date:
    """Prefer explicit period end; else Indian FY end containing max txn date."""
    if explicit:
        return explicit
    parsed = [d for d in (_as_date(x) for x in dates) if d]
    if not parsed:
        today = date.today()
        return date(today.year if today.month >= 4 else today.year - 1, 3, 31)
    latest = max(parsed)
    # Indian FY ends 31 March
    if latest.month >= 4:
        return date(latest.year + 1, 3, 31)
    return date(latest.year, 3, 31)


def compute_materiality(
    amounts: Iterable[float],
    turnover_hint: float | None = None,
    asset_hint: float | None = None,
    override: float | None = None,
) -> dict[str, float]:
    """
    Planning materiality heuristics used by mid-market CA practices:
      - 1%–5% of turnover (default 2%)
      - or 1% of gross assets
      - performance materiality ≈ 75% of planning materiality
      - clearly trivial threshold ≈ 5% of performance materiality
    """
    vals = [abs(float(a or 0)) for a in amounts]
    population = float(sum(vals))
    turnover = float(turnover_hint) if turnover_hint else population
    assets = float(asset_hint) if asset_hint else population
    if override and override > 0:
        planning = float(override)
    else:
        planning = max(turnover * 0.02, assets * 0.01, 50000.0)
        # Cap absurdly large materiality on tiny books
        if population > 0:
            planning = min(planning, max(population * 0.1, 50000.0))
    performance = planning * 0.75
    trivial = performance * 0.05
    return {
        "planning_materiality": round(planning, 2),
        "performance_materiality": round(performance, 2),
        "clearly_trivial": round(trivial, 2),
        "population_amount": round(population, 2),
        "turnover_base": round(turnover, 2),
    }


def _meta(row: dict) -> dict:
    meta = row.get("audit_meta") or {}
    if not isinstance(meta, dict):
        return {}
    return meta


def run_assertion_procedures(
    rows: Iterable,
    period_end: date | None = None,
    materiality_override: float | None = None,
    cutoff_window_days: int = 7,
) -> dict[str, Any]:
    """
    Run full assertion battery over a transaction log.

    Returns:
      materiality, period_end, population, per_transaction assertion scores,
      findings (typed), coverage summary.
    """
    frame = transactions_to_frame(rows)
    if frame.empty:
        mat = compute_materiality([])
        return {
            "materiality": mat,
            "period_end": None,
            "population": {"count": 0, "amount": 0.0},
            "transaction_assertions": {},
            "findings": [],
            "coverage": {"assertions_tested": list(ASSERTION_TYPES), "findings": 0},
        }

    # Enrich frame with optional audit_meta fields from original rows
    meta_by_id: dict[str, dict] = {}
    for row in rows:
        if isinstance(row, dict):
            tid = str(row.get("id", ""))
            meta_by_id[tid] = row.get("audit_meta") or {}
            for key in ("account_code", "je_id", "po_number", "grn_number", "due_date",
                        "related_party", "period_end", "debit_credit", "payment_status"):
                if key in row and key not in meta_by_id[tid]:
                    meta_by_id[tid][key] = row[key]
        else:
            tid = str(getattr(row, "id", ""))
            meta = getattr(row, "audit_meta", None) or {}
            if not isinstance(meta, dict):
                meta = {}
            meta_by_id[tid] = dict(meta)

    frame["id"] = frame["id"].astype(str)
    amounts = pd.to_numeric(frame.get("amount", 0), errors="coerce").fillna(0.0)
    frame["_amount"] = amounts.abs()
    dates = [_as_date(d) for d in frame.get("date", [])]
    frame["_date"] = dates

    # Period end from meta or inference
    explicit_pe = period_end
    if explicit_pe is None:
        for meta in meta_by_id.values():
            pe = _as_date(meta.get("period_end"))
            if pe:
                explicit_pe = pe
                break
    pe = infer_period_end(dates, explicit_pe)
    mat = compute_materiality(amounts.tolist(), override=materiality_override)
    pm = mat["performance_materiality"]
    trivial = mat["clearly_trivial"]

    # Invoice sequence gaps per vendor (completeness)
    vendor_invoices: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for _, row in frame.iterrows():
        inv = str(row.get("invoice_no") or "")
        vendor = str(row.get("vendor_gstin") or "")
        digits = "".join(ch for ch in inv if ch.isdigit())
        if digits:
            vendor_invoices[vendor].append((str(row["id"]), digits))

    sequence_gap_ids: set[str] = set()
    for vendor, items in vendor_invoices.items():
        nums = sorted({int(d) for _, d in items if d.isdigit()})
        if len(nums) < 3:
            continue
        gaps = []
        for a, b in zip(nums, nums[1:]):
            if 1 < (b - a) <= 5:  # small gaps look like missing vouchers
                gaps.append((a, b))
        if gaps:
            # Flag the later invoices after a gap as completeness risk
            gap_after = {b for _, b in gaps}
            for tid, digs in items:
                if digs.isdigit() and int(digs) in gap_after:
                    sequence_gap_ids.add(tid)

    # Same-amount same-day clusters (JE / split booking style)
    cluster_keys = frame.assign(
        _day=frame["_date"].astype(str),
        _amt=frame["_amount"].round(0),
    ).groupby(["vendor_gstin", "_day", "_amt"])["id"].transform("count")
    frame["_cluster_n"] = cluster_keys

    # PAN/state shared across vendors for RP proxy (GSTIN positions 3-12 = PAN)
    pan_to_vendors: dict[str, set[str]] = defaultdict(set)
    for gstin in frame.get("vendor_gstin", pd.Series(dtype=str)).fillna(""):
        g = str(gstin)
        if len(g) >= 12:
            pan_to_vendors[g[2:12]].add(g)
    shared_pan_vendors = {v for vendors in pan_to_vendors.values() if len(vendors) > 1 for v in vendors}

    findings: list[dict[str, Any]] = []
    per_txn: dict[str, dict[str, Any]] = {}

    match = frame.get("match_status", pd.Series(["unmatched"] * len(frame))).fillna("unmatched")
    fraud = frame.get("fraud_flag")

    for idx, row in frame.iterrows():
        tid = str(row["id"])
        meta = meta_by_id.get(tid, {})
        amount = float(row["_amount"] or 0)
        txn_date = row["_date"]
        assertions: dict[str, dict[str, Any]] = {}
        score_parts = []

        # --- Cut-off ---
        cutoff_hit = False
        cutoff_detail = None
        if txn_date and pe:
            delta = (txn_date - pe).days
            if abs(delta) <= cutoff_window_days:
                cutoff_hit = True
                side = "pre" if delta <= 0 else "post"
                cutoff_detail = {
                    "window_days": cutoff_window_days,
                    "days_from_period_end": delta,
                    "side": side,
                    "procedure": "Vouch shipping/delivery/recognition evidence for period cut-off.",
                }
                # Post-period invoices booked into prior period (or vice versa) are higher risk
                severity = 0.85 if abs(delta) <= 2 else 0.65
                if amount >= pm * 0.1:
                    severity = min(1.0, severity + 0.1)
                score_parts.append(severity)
        assertions["cutoff"] = {
            "failed": cutoff_hit,
            "score": round(score_parts[-1] if cutoff_hit else 0.0, 4),
            "detail": cutoff_detail,
        }

        # --- Completeness ---
        completeness_reasons = []
        completeness_score = 0.0
        if tid in sequence_gap_ids:
            completeness_reasons.append("invoice_sequence_gap")
            completeness_score = max(completeness_score, 0.7)
        if not str(row.get("invoice_no") or "").strip():
            completeness_reasons.append("missing_invoice_number")
            completeness_score = max(completeness_score, 0.55)
        if str(match.loc[idx]) == "unmatched" and amount >= trivial:
            completeness_reasons.append("unmatched_to_gst_2b")
            completeness_score = max(completeness_score, 0.6)
        assertions["completeness"] = {
            "failed": bool(completeness_reasons),
            "score": round(completeness_score, 4),
            "detail": {
                "reasons": completeness_reasons,
                "procedure": "Trace source documents into the books; investigate missing invoice sequence.",
            } if completeness_reasons else None,
        }
        if completeness_score:
            score_parts.append(completeness_score)

        # --- Existence ---
        existence_reasons = []
        existence_score = 0.0
        if str(match.loc[idx]) == "unmatched" and amount >= trivial:
            existence_reasons.append("no_gst_match_support")
            existence_score = max(existence_score, 0.55)
        if not str(row.get("fingerprint") or "").strip() and amount >= pm * 0.05:
            existence_reasons.append("missing_document_fingerprint")
            existence_score = max(existence_score, 0.45)
        po = meta.get("po_number")
        grn = meta.get("grn_number")
        if po is False or (meta.get("three_way") == "fail"):
            existence_reasons.append("three_way_stated_fail")
            existence_score = max(existence_score, 0.8)
        if po and not grn:
            existence_reasons.append("po_without_grn")
            existence_score = max(existence_score, 0.5)
        assertions["existence"] = {
            "failed": bool(existence_reasons),
            "score": round(existence_score, 4),
            "detail": {
                "reasons": existence_reasons,
                "procedure": "Vouch to PO/GRN/payment/bank evidence for occurrence/existence.",
            } if existence_reasons else None,
        }
        if existence_score:
            score_parts.append(existence_score)

        # --- Classification / accuracy ---
        tax = float(row.get("tax_amount") or 0)
        tax_ratio = (tax / amount) if amount > 1e-6 else 0.0
        standard = [0.0, 0.05, 0.12, 0.18, 0.28]
        class_reasons = []
        class_score = 0.0
        if tax > 0 and amount > 0 and not any(abs(tax_ratio - r) < 0.015 for r in standard):
            class_reasons.append(f"non_standard_tax_ratio:{tax_ratio:.3f}")
            class_score = max(class_score, 0.7)
        if 45000 <= amount < 50000:
            class_reasons.append("threshold_gaming_band")
            class_score = max(class_score, 0.65)
        if fraud is not None and pd.notna(fraud.loc[idx]) and str(fraud.loc[idx]).strip():
            class_reasons.append("fraud_scanner_flag")
            class_score = max(class_score, 0.8)
        acct = str(meta.get("account_code") or "")
        nature = str(meta.get("classification") or meta.get("account_nature") or "").lower()
        if nature in {"capex", "asset"} and "expense" in acct.lower():
            class_reasons.append("capex_posted_to_expense")
            class_score = max(class_score, 0.75)
        assertions["classification"] = {
            "failed": bool(class_reasons),
            "score": round(class_score, 4),
            "detail": {
                "reasons": class_reasons,
                "procedure": "Recalculate tax and confirm account classification against supporting docs.",
            } if class_reasons else None,
        }
        if class_score:
            score_parts.append(class_score)
        assertions["accuracy"] = assertions["classification"]  # shared precision tests

        # --- Related party ---
        rp_reasons = []
        rp_score = 0.0
        gstin = str(row.get("vendor_gstin") or "")
        if meta.get("related_party") in (True, "true", "yes", 1, "1"):
            rp_reasons.append("marked_related_party")
            rp_score = max(rp_score, 0.7)
        if gstin in shared_pan_vendors:
            rp_reasons.append("shared_pan_across_vendors")
            rp_score = max(rp_score, 0.6)
        assertions["related_party"] = {
            "failed": bool(rp_reasons),
            "score": round(rp_score, 4),
            "detail": {
                "reasons": rp_reasons,
                "procedure": "Review related-party register and arm's-length pricing.",
            } if rp_reasons else None,
        }
        if rp_score:
            score_parts.append(rp_score)

        # --- Journal entry style ---
        je_reasons = []
        je_score = 0.0
        if amount > 10000 and amount % 1000 == 0:
            je_reasons.append("round_thousand")
            je_score = max(je_score, 0.45)
        if txn_date and txn_date.weekday() >= 5:
            je_reasons.append("weekend_posting")
            je_score = max(je_score, 0.4)
        if float(row.get("_cluster_n") or 0) >= 3:
            je_reasons.append("same_day_same_amount_split")
            je_score = max(je_score, 0.7)
        if meta.get("je_id") and meta.get("manual_entry") in (True, "true", 1, "1"):
            je_reasons.append("manual_journal")
            je_score = max(je_score, 0.55)
        if cutoff_hit and amount >= trivial and amount % 1000 == 0:
            je_reasons.append("period_end_round_amount")
            je_score = max(je_score, 0.8)
        assertions["journal_entry"] = {
            "failed": bool(je_reasons),
            "score": round(je_score, 4),
            "detail": {
                "reasons": je_reasons,
                "procedure": "Inspect JE/voucher authorisation, supporting memos, and posting user.",
            } if je_reasons else None,
        }
        if je_score:
            score_parts.append(je_score)

        # --- Three-way / GST match ---
        mstatus = str(match.loc[idx] or "unmatched")
        conf = float(row.get("match_confidence") or 0)
        tw_score = 0.0
        tw_reasons = []
        if mstatus == "unmatched":
            tw_reasons.append("unmatched")
            tw_score = 0.75 if amount >= trivial else 0.45
        elif mstatus == "fuzzy":
            tw_reasons.append("fuzzy_match_only")
            tw_score = 0.55
        elif mstatus == "tolerance":
            tw_reasons.append("tolerance_match")
            tw_score = 0.35
        if conf and conf < 70 and mstatus != "exact":
            tw_reasons.append("low_match_confidence")
            tw_score = max(tw_score, 0.5)
        if meta.get("po_number") and meta.get("grn_number") and meta.get("price_variance"):
            try:
                if abs(float(meta["price_variance"])) > max(trivial, amount * 0.02):
                    tw_reasons.append("po_price_variance")
                    tw_score = max(tw_score, 0.7)
            except (TypeError, ValueError):
                pass
        assertions["three_way_match"] = {
            "failed": bool(tw_reasons),
            "score": round(tw_score, 4),
            "detail": {
                "reasons": tw_reasons,
                "match_status": mstatus,
                "procedure": "Perform PO–GRN–invoice three-way match / GST books-to-2B vouching.",
            } if tw_reasons else None,
        }
        if tw_score:
            score_parts.append(tw_score)

        # --- Aging ---
        aging_score = 0.0
        aging_reasons = []
        due = _as_date(meta.get("due_date"))
        pay_status = str(meta.get("payment_status") or "").lower()
        age_days = None
        if due and pe:
            age_days = (pe - due).days
        elif txn_date and pe:
            age_days = (pe - txn_date).days
        if age_days is not None and age_days > 90 and pay_status not in {"paid", "settled", "cleared"}:
            aging_reasons.append(f"open_over_{age_days}_days")
            aging_score = 0.55 if age_days <= 180 else 0.75
        if age_days is not None and age_days > 45 and meta.get("msme"):
            aging_reasons.append("msme_overdue_45")
            aging_score = max(aging_score, 0.7)
        assertions["aging"] = {
            "failed": bool(aging_reasons),
            "score": round(aging_score, 4),
            "detail": {
                "reasons": aging_reasons,
                "age_days": age_days,
                "procedure": "Review ageing, subsequent receipts/payments, and provisioning.",
            } if aging_reasons else None,
        }
        if aging_score:
            score_parts.append(aging_score)

        # Compound like a human auditor: multiple failed assertions escalate sharply
        failed = [k for k, v in assertions.items() if v.get("failed")]
        if not score_parts:
            assertion_risk = 0.05
        else:
            base = float(np.max(score_parts))
            compound = min(0.25, 0.08 * max(0, len(set(failed)) - 1))
            # Material items get attention even at moderate assertion risk
            material_boost = 0.1 if amount >= pm else (0.05 if amount >= trivial else 0.0)
            assertion_risk = float(np.clip(base + compound + material_boost, 0.0, 1.0))

        # Evidence confidence: how complete is the voucher trail?
        evidence_bits = [
            bool(str(row.get("invoice_no") or "").strip()),
            bool(str(row.get("vendor_gstin") or "").strip()),
            bool(str(row.get("fingerprint") or "").strip()),
            mstatus in {"exact", "tolerance"},
            bool(meta.get("po_number") or meta.get("grn_number") or meta.get("account_code")),
        ]
        confidence = round(sum(1 for b in evidence_bits if b) / len(evidence_bits), 4)

        evidence = {
            "invoice_no": row.get("invoice_no"),
            "vendor_gstin": row.get("vendor_gstin"),
            "vendor_name": row.get("vendor_name"),
            "amount": amount,
            "date": txn_date.isoformat() if txn_date else None,
            "match_status": mstatus,
            "fingerprint": row.get("fingerprint") or None,
            "audit_meta": {k: meta[k] for k in meta if k in {
                "account_code", "je_id", "po_number", "grn_number", "due_date",
                "related_party", "payment_status", "classification",
            }},
            "failed_assertions": failed,
            "recommended_procedures": [
                assertions[a]["detail"]["procedure"]
                for a in failed
                if assertions[a].get("detail") and assertions[a]["detail"].get("procedure")
            ],
        }

        per_txn[tid] = {
            "assertion_risk": round(assertion_risk, 4),
            "confidence": confidence,
            "failed_assertions": failed,
            "assertions": assertions,
            "evidence": evidence,
            "material": amount >= pm,
            "above_trivial": amount >= trivial,
            "amount": amount,
        }

        if failed and (amount >= trivial or assertion_risk >= 0.55):
            findings.append({
                "transaction_id": tid,
                "assertion_risk": round(assertion_risk, 4),
                "failed_assertions": failed,
                "amount": amount,
                "material": amount >= pm,
                "evidence": evidence,
                "primary_assertion": max(
                    ((a, assertions[a]["score"]) for a in failed),
                    key=lambda x: x[1],
                )[0] if failed else None,
            })

    findings.sort(key=lambda f: (-f["assertion_risk"], -f["amount"]))

    # Population coverage diagnostics
    material_ids = [tid for tid, v in per_txn.items() if v["material"]]
    high_risk_ids = [tid for tid, v in per_txn.items() if v["assertion_risk"] >= 0.65]
    assertion_counts = Counter(
        a for v in per_txn.values() for a in v["failed_assertions"]
    )

    return {
        "materiality": mat,
        "period_end": pe.isoformat(),
        "population": {
            "count": int(len(frame)),
            "amount": round(float(frame["_amount"].sum()), 2),
            "material_count": len(material_ids),
            "high_assertion_risk_count": len(high_risk_ids),
        },
        "transaction_assertions": per_txn,
        "findings": findings[:500],
        "coverage": {
            "assertions_tested": list(ASSERTION_TYPES),
            "findings": len(findings),
            "assertion_failure_counts": dict(assertion_counts),
            "material_population_ids": material_ids[:200],
            "high_risk_ids": high_risk_ids[:200],
        },
    }


def assertion_scores_map(result: dict[str, Any]) -> dict[str, float]:
    return {
        tid: float(payload.get("assertion_risk") or 0.0)
        for tid, payload in (result.get("transaction_assertions") or {}).items()
    }


def confidence_map(result: dict[str, Any]) -> dict[str, float]:
    return {
        tid: float(payload.get("confidence") or 0.0)
        for tid, payload in (result.get("transaction_assertions") or {}).items()
    }
