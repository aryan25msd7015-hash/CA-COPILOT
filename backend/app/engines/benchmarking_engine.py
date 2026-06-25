"""Consent-based cross-client benchmarking."""
from statistics import median

from app.models.client import Client
from app.models.document import Document

RATIO_KEYS = ("current_ratio", "debt_equity_ratio", "gross_margin_pct", "asset_turnover")


def _latest_ratios(client_id: str, db) -> dict:
    doc = (
        db.query(Document)
        .filter(Document.client_id == client_id, Document.doc_type == "trial_balance")
        .order_by(Document.created_at.desc())
        .first()
    )
    data = (doc.ocr_json or {}).get("audit_result", {}) if doc else {}
    return data.get("ratios", {})


def _latest_ratios_for_clients(client_ids: list[str], db) -> dict[str, dict]:
    if not client_ids:
        return {}
    docs = (
        db.query(Document)
        .filter(Document.client_id.in_(client_ids), Document.doc_type == "trial_balance")
        .order_by(Document.client_id.asc(), Document.created_at.desc())
        .all()
    )
    ratios: dict[str, dict] = {}
    for doc in docs:
        key = str(doc.client_id)
        if key in ratios:
            continue
        data = (doc.ocr_json or {}).get("audit_result", {})
        ratios[key] = data.get("ratios", {})
    return ratios


def get_benchmark_pool(industry: str, exclude_org_id: str, db) -> list[Client]:
    return (
        db.query(Client)
        .filter(
            Client.industry == industry,
            Client.benchmark_consent_at.isnot(None),
            Client.org_id != exclude_org_id,
        )
        .all()
    )


def get_demo_benchmark_pool(industry: str, org_id: str, exclude_client_id: str, db) -> list[Client]:
    """Use only consenting same-org peers when external pool is too small."""
    return (
        db.query(Client)
        .filter(
            Client.industry == industry,
            Client.benchmark_consent_at.isnot(None),
            Client.org_id == org_id,
            Client.id != exclude_client_id,
        )
        .all()
    )


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    idx = (len(ordered) - 1) * pct
    lower, upper = int(idx), min(int(idx) + 1, len(ordered) - 1)
    weight = idx - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def compute_industry_benchmarks(industry: str, exclude_org_id: str, db) -> dict | None:
    pool = get_benchmark_pool(industry, exclude_org_id, db)
    if len(pool) < 5:
        return None
    ratio_map = _latest_ratios_for_clients([str(client.id) for client in pool], db)
    metrics = {}
    for key in RATIO_KEYS:
        values = [float(ratios[key]) for ratios in ratio_map.values() if key in ratios]
        if values:
            metrics[key] = {
                "median": round(median(values), 2),
                "p25": round(_percentile(values, 0.25), 2),
                "p75": round(_percentile(values, 0.75), 2),
            }
    return {"industry": industry, "peer_count": len(pool), "metrics": metrics}


def _metric_status(metric: str, client_value: float, benchmark: dict) -> dict:
    median_value = float(benchmark.get("median", 0) or 0)
    delta = round(client_value - median_value, 2)
    pct_delta = round((delta / abs(median_value)) * 100, 2) if median_value else 0
    lower_is_better = metric in {"debt_equity_ratio"}
    if benchmark.get("p25") is None or benchmark.get("p75") is None:
        band = "insufficient"
    elif lower_is_better:
        if client_value <= benchmark["p25"]:
            band = "better_than_peers"
        elif client_value >= benchmark["p75"]:
            band = "worse_than_peers"
        else:
            band = "in_range"
    else:
        if client_value >= benchmark["p75"]:
            band = "better_than_peers"
        elif client_value <= benchmark["p25"]:
            band = "worse_than_peers"
        else:
            band = "in_range"
    return {"delta_to_median": delta, "pct_delta_to_median": pct_delta, "band": band}


def compare_client(client_id: str, db) -> dict:
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise ValueError("Client not found")
    benchmarks = compute_industry_benchmarks(client.industry or "", str(client.org_id), db)
    peer_source = "cross_org_anonymized"
    if not benchmarks:
        pool = get_demo_benchmark_pool(client.industry or "", str(client.org_id), str(client.id), db)
        if len(pool) >= 2:
            ratio_map = _latest_ratios_for_clients([str(peer.id) for peer in pool], db)
            metrics = {}
            for key in RATIO_KEYS:
                values = [float(ratios[key]) for ratios in ratio_map.values() if key in ratios]
                if values:
                    metrics[key] = {
                        "median": round(median(values), 2),
                        "p25": round(_percentile(values, 0.25), 2),
                        "p75": round(_percentile(values, 0.75), 2),
                    }
            benchmarks = {"industry": client.industry, "peer_count": len(pool), "metrics": metrics}
            peer_source = "same_org_demo_pool"
    client_ratios = _latest_ratios(client_id, db)
    metric_comparisons = {}
    if benchmarks:
        for key, value in client_ratios.items():
            if key in benchmarks["metrics"]:
                metric_comparisons[key] = {
                    "client": float(value),
                    **benchmarks["metrics"][key],
                    **_metric_status(key, float(value), benchmarks["metrics"][key]),
                }
    return {
        "client_id": str(client.id),
        "client_name": client.name,
        "industry": client.industry,
        "client_ratios": client_ratios,
        "benchmarks": benchmarks["metrics"] if benchmarks else None,
        "peer_count": benchmarks["peer_count"] if benchmarks else 0,
        "peer_source": peer_source if benchmarks else "insufficient",
        "minimum_peer_count": 5,
        "metric_comparisons": metric_comparisons,
    }
