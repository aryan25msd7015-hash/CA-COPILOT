"""Graph-based GSTIN collusion / shell-vendor engine (HAE Layer 3).

Implements a GraphSAGE-style mean-aggregation encoder when PyTorch is available,
and a pure-numpy graph feature scorer otherwise (degree, shared-vendor density,
triangle proxies via common neighbors).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

from app.engines import model_registry
from app.engines.feature_engineering import transactions_to_frame

logger = logging.getLogger(__name__)

GNN_MODEL_NAME = "hae_graph_sage"


def _try_torch():
    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F

        return torch, nn, F
    except Exception:
        return None, None, None


def _log1p(x: float) -> float:
    return float(np.log1p(max(float(x), 0.0)))


def build_vendor_graph(df: pd.DataFrame) -> dict[str, Any]:
    """Build bipartite-derived vendor graph features from transactions."""
    empty = {
        "vendor_ids": [],
        "node_features": np.zeros((0, 6)),
        "edge_index": np.zeros((2, 0), dtype=int),
        "txn_to_vendor": {},
        "vendor_scores_numpy": {},
    }
    if df is None or df.empty:
        return empty

    work = df.copy()
    work["amount"] = pd.to_numeric(work.get("amount", 0), errors="coerce").fillna(0.0)
    work["vendor_gstin"] = work.get("vendor_gstin", pd.Series([""] * len(work))).fillna("").astype(str)
    work["client_id"] = work.get("client_id", pd.Series([""] * len(work))).fillna("").astype(str)
    work = work[work["vendor_gstin"].str.len() > 0]
    if work.empty:
        return empty

    vendors = sorted(work["vendor_gstin"].unique().tolist())
    v_index = {v: i for i, v in enumerate(vendors)}

    client_vendors: dict[str, set[str]] = defaultdict(set)
    vendor_clients: dict[str, set[str]] = defaultdict(set)
    vendor_amounts: dict[str, list[float]] = defaultdict(list)
    vendor_txn_ids: dict[str, list[str]] = defaultdict(list)

    for _, row in work.iterrows():
        v = str(row["vendor_gstin"])
        c = str(row["client_id"])
        client_vendors[c].add(v)
        vendor_clients[v].add(c)
        vendor_amounts[v].append(float(row["amount"]))
        vendor_txn_ids[v].append(str(row.get("id")))

    edges = set()
    for vendors_for_client in client_vendors.values():
        vs = list(vendors_for_client)
        for i in range(len(vs)):
            for j in range(i + 1, len(vs)):
                a, b = v_index[vs[i]], v_index[vs[j]]
                edges.add((a, b))
                edges.add((b, a))
    edge_index = np.array(sorted(edges), dtype=int).T if edges else np.zeros((2, 0), dtype=int)

    degrees = np.zeros(len(vendors))
    if edge_index.size:
        for src in edge_index[0]:
            degrees[int(src)] += 1

    neighbor_sets = [set() for _ in vendors]
    if edge_index.size:
        for src, dst in edge_index.T:
            neighbor_sets[int(src)].add(int(dst))

    feats = []
    numpy_scores = {}
    total_amount = max(float(work["amount"].abs().sum()), 1.0)
    for i, v in enumerate(vendors):
        amts = vendor_amounts[v]
        mean_a = float(np.mean(amts)) if amts else 0.0
        std_a = float(np.std(amts)) if len(amts) > 1 else 0.0
        n_clients = float(len(vendor_clients[v]))
        share = float(sum(abs(a) for a in amts) / total_amount)
        dens = 0.0
        if neighbor_sets[i]:
            inter = 0
            for nb in neighbor_sets[i]:
                inter += len(neighbor_sets[i] & neighbor_sets[nb])
            dens = inter / max(len(neighbor_sets[i]) ** 2, 1)
        feats.append(np.array([
            _log1p(degrees[i]),
            n_clients,
            _log1p(mean_a),
            _log1p(std_a),
            share,
            dens,
        ], dtype=np.float32))
        risk = 1.0 - np.exp(-(
            0.8 * dens
            + 0.4 * min(n_clients / 5.0, 1.0)
            + 0.5 * share
            + 0.2 * min(degrees[i] / 10.0, 1.0)
        ))
        numpy_scores[v] = float(np.clip(risk, 0.0, 1.0))

    txn_to_vendor = {
        tid: v for v, tids in vendor_txn_ids.items() for tid in tids
    }
    return {
        "vendor_ids": vendors,
        "node_features": np.vstack(feats) if feats else np.zeros((0, 6)),
        "edge_index": edge_index,
        "txn_to_vendor": txn_to_vendor,
        "vendor_scores_numpy": numpy_scores,
    }


def _build_graphsage(torch, nn, F, in_dim: int = 6, hidden: int = 16):
    class TinyGraphSAGE(nn.Module):
        def __init__(self):
            super().__init__()
            self.lin_self = nn.Linear(in_dim, hidden)
            self.lin_neigh = nn.Linear(in_dim, hidden)
            self.out = nn.Sequential(
                nn.Linear(hidden, 8), nn.ReLU(), nn.Linear(8, 1), nn.Sigmoid()
            )

        def forward(self, x, edge_index):
            if edge_index.numel() == 0:
                h = F.relu(self.lin_self(x))
                return self.out(h).squeeze(-1)
            src, dst = edge_index[0], edge_index[1]
            neigh = torch.zeros_like(x)
            deg = torch.zeros(x.size(0), device=x.device)
            ones = torch.ones(src.size(0), device=x.device)
            neigh.index_add_(0, dst, x[src])
            deg.index_add_(0, dst, ones)
            neigh = neigh / deg.clamp(min=1.0).unsqueeze(-1)
            h = F.relu(self.lin_self(x) + self.lin_neigh(neigh))
            return self.out(h).squeeze(-1)

    return TinyGraphSAGE()


def fit_graph_model(rows, org_id: str | None = None, epochs: int = 12) -> dict:
    graph = build_vendor_graph(transactions_to_frame(rows))
    torch, nn, F = _try_torch()
    meta = {
        "n_vendors": len(graph["vendor_ids"]),
        "n_edges": int(graph["edge_index"].shape[1]),
        "backend": "numpy",
    }
    if torch is None or len(graph["vendor_ids"]) < 3:
        bundle = {"backend": "numpy", "vendor_scores": graph["vendor_scores_numpy"]}
        model_registry.save_artifact(org_id, GNN_MODEL_NAME, bundle, meta)
        return {**meta, "trained": False}

    x = torch.tensor(graph["node_features"], dtype=torch.float32)
    edge_index = torch.tensor(graph["edge_index"], dtype=torch.long)
    y = torch.tensor(
        [graph["vendor_scores_numpy"].get(v, 0.5) for v in graph["vendor_ids"]],
        dtype=torch.float32,
    )
    model = _build_graphsage(torch, nn, F, in_dim=x.shape[1])
    opt = torch.optim.Adam(model.parameters(), lr=1e-2)
    loss_fn = nn.BCELoss()
    model.train()
    last_loss = None
    for _ in range(epochs):
        opt.zero_grad()
        pred = model(x, edge_index)
        loss = loss_fn(pred, y)
        loss.backward()
        opt.step()
        last_loss = float(loss.detach().cpu())
    bundle = {
        "backend": "torch",
        "state_dict": {k: v.detach().cpu() for k, v in model.state_dict().items()},
        "in_dim": int(x.shape[1]),
        "vendor_ids": graph["vendor_ids"],
        "last_loss": last_loss,
    }
    meta.update({"backend": "torch", "last_loss": last_loss})
    model_registry.save_artifact(org_id, GNN_MODEL_NAME, bundle, meta)
    return {**meta, "trained": True}


def score_graph(rows, org_id: str | None = None) -> dict[str, float]:
    """Return transaction_id -> graph collusion risk."""
    frame = transactions_to_frame(rows)
    graph = build_vendor_graph(frame)
    if not graph["txn_to_vendor"]:
        return {}

    vendor_scores = dict(graph["vendor_scores_numpy"])
    bundle = model_registry.load_artifact(org_id, GNN_MODEL_NAME) or {"backend": "numpy"}
    torch, nn, F = _try_torch()
    if bundle.get("backend") == "torch" and torch is not None and bundle.get("state_dict"):
        try:
            x = torch.tensor(graph["node_features"], dtype=torch.float32)
            edge_index = torch.tensor(graph["edge_index"], dtype=torch.long)
            model = _build_graphsage(torch, nn, F, in_dim=int(bundle.get("in_dim") or x.shape[1]))
            model.load_state_dict(bundle["state_dict"])
            model.eval()
            with torch.no_grad():
                pred = model(x, edge_index).cpu().numpy()
            for i, v in enumerate(graph["vendor_ids"]):
                vendor_scores[v] = float(np.clip(pred[i], 0.0, 1.0))
        except Exception as exc:
            logger.debug("Torch GNN score failed: %s", exc)

    return {
        tid: float(vendor_scores.get(vendor, 0.5))
        for tid, vendor in graph["txn_to_vendor"].items()
    }


def graph_risk_summary(rows, org_id: str | None = None) -> list[dict]:
    frame = transactions_to_frame(rows)
    graph = build_vendor_graph(frame)
    txn_scores = score_graph(rows, org_id=org_id)
    vendor_max: dict[str, float] = defaultdict(float)
    for tid, vendor in graph["txn_to_vendor"].items():
        vendor_max[vendor] = max(vendor_max[vendor], txn_scores.get(tid, 0.0))
    return sorted(
        [
            {
                "vendor_gstin": v,
                "graph_risk": round(r, 4),
                "degree_proxy": round(float(graph["vendor_scores_numpy"].get(v, 0.0)), 4),
            }
            for v, r in vendor_max.items()
        ],
        key=lambda row: -row["graph_risk"],
    )[:20]
