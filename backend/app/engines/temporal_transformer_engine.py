"""Temporal sequence anomaly engine (HAE Layer 3).

Uses a lightweight Transformer encoder when PyTorch is available; otherwise a
numpy statistical sequence scorer (z-score + lag residual) that preserves API.
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.engines import model_registry
from app.engines.feature_engineering import transactions_to_frame

logger = logging.getLogger(__name__)

TFT_MODEL_NAME = "hae_temporal_transformer"
SEQ_LEN = 16
SEQ_FEATURES = ["amount", "tax_ratio", "day_of_week", "match_code", "log_amount"]


def _try_torch():
    try:
        import torch
        import torch.nn as nn

        return torch, nn
    except Exception:
        return None, None


def _match_code(status: str) -> float:
    return {"exact": 0.0, "tolerance": 0.33, "fuzzy": 0.66, "unmatched": 1.0}.get(
        (status or "unmatched").lower(), 1.0
    )


def build_vendor_sequences(df: pd.DataFrame, seq_len: int = SEQ_LEN) -> tuple[np.ndarray, list[str], list[str]]:
    """Return (X [N,T,F], transaction_ids aligned to last step, vendor keys)."""
    if df is None or df.empty:
        return np.zeros((0, seq_len, len(SEQ_FEATURES))), [], []

    work = df.copy()
    work["amount"] = pd.to_numeric(work.get("amount", 0), errors="coerce").fillna(0.0)
    work["tax_amount"] = pd.to_numeric(work.get("tax_amount", 0), errors="coerce").fillna(0.0)
    work["tax_ratio"] = np.where(work["amount"].abs() > 1e-6, work["tax_amount"] / work["amount"].abs(), 0.0)
    work["log_amount"] = np.log1p(work["amount"].abs())
    dates = pd.to_datetime(work.get("date"), errors="coerce")
    work["day_of_week"] = dates.dt.dayofweek.fillna(0).astype(float)
    work["match_code"] = work.get("match_status", pd.Series(["unmatched"] * len(work))).map(_match_code).astype(float)
    work["_date"] = dates
    work = work.sort_values(["vendor_gstin", "_date", "id"], kind="mergesort")

    Xs = []
    ids = []
    vendors = []
    for vendor, group in work.groupby(work.get("vendor_gstin", pd.Series([""] * len(work))).fillna(""), sort=False):
        feats = group[SEQ_FEATURES].astype(float).values
        tid = group["id"].astype(str).tolist() if "id" in group.columns else [str(i) for i in range(len(group))]
        for i in range(len(group)):
            start = max(0, i + 1 - seq_len)
            window = feats[start : i + 1]
            if len(window) < seq_len:
                pad = np.zeros((seq_len - len(window), len(SEQ_FEATURES)))
                window = np.vstack([pad, window])
            Xs.append(window)
            ids.append(tid[i])
            vendors.append(str(vendor))
    if not Xs:
        return np.zeros((0, seq_len, len(SEQ_FEATURES))), [], []
    return np.asarray(Xs, dtype=np.float32), ids, vendors


def _numpy_sequence_scores(X: np.ndarray) -> np.ndarray:
    """Fallback: score by deviation of last amount vs vendor window mean/std."""
    if len(X) == 0:
        return np.array([])
    amounts = X[:, :, 0]
    last = amounts[:, -1]
    # ignore padded zeros when estimating mean
    means = []
    stds = []
    for row in amounts:
        nonzero = row[row > 0]
        if len(nonzero) == 0:
            means.append(0.0)
            stds.append(1.0)
        else:
            means.append(float(nonzero.mean()))
            stds.append(float(max(nonzero.std(), abs(nonzero.mean()) * 0.05, 1.0)))
    means = np.asarray(means)
    stds = np.asarray(stds)
    z = np.abs(last - means) / stds
    # also penalize sudden tax_ratio jumps
    tax = X[:, :, 1]
    tax_delta = np.abs(tax[:, -1] - np.median(tax, axis=1))
    risk = 1.0 - np.exp(-(z / 3.0)) * np.exp(-(tax_delta * 2.0))
    return np.clip(risk, 0.0, 1.0)


def _build_torch_model(nn, n_features: int, d_model: int = 32, nhead: int = 4, nlayers: int = 2):
    class TinyTemporalTransformer(nn.Module):
        def __init__(self):
            super().__init__()
            self.input = nn.Linear(n_features, d_model)
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=d_model, nhead=nhead, dim_feedforward=64, batch_first=True, dropout=0.1
            )
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=nlayers)
            self.head = nn.Sequential(nn.Linear(d_model, 16), nn.ReLU(), nn.Linear(16, 1), nn.Sigmoid())

        def forward(self, x):
            h = self.input(x)
            h = self.encoder(h)
            return self.head(h[:, -1, :]).squeeze(-1)

    return TinyTemporalTransformer()


def fit_temporal_model(rows, org_id: str | None = None, epochs: int = 8) -> dict:
    """Train temporal model; falls back to numpy scorer stats when torch missing."""
    frame = transactions_to_frame(rows)
    X, ids, vendors = build_vendor_sequences(frame)
    torch, nn = _try_torch()
    meta = {"n_sequences": len(X), "backend": "numpy"}
    if torch is None or len(X) < 16:
        # Store vendor rolling baselines for numpy scorer reproducibility
        bundle = {"backend": "numpy", "seq_len": SEQ_LEN}
        model_registry.save_artifact(org_id, TFT_MODEL_NAME, bundle, meta)
        return {**meta, "trained": False, "reason": "torch_unavailable_or_few_rows"}

    model = _build_torch_model(nn, n_features=X.shape[-1])
    # Self-supervised: reconstruct last amount magnitude via proxy labels from z-score thresholds
    y = _numpy_sequence_scores(X)
    # Convert soft anomaly scores into training targets (higher = more anomalous)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.BCELoss()
    model.train()
    dataset = torch.utils.data.TensorDataset(
        torch.tensor(X, dtype=torch.float32),
        torch.tensor(y, dtype=torch.float32),
    )
    loader = torch.utils.data.DataLoader(dataset, batch_size=min(64, len(X)), shuffle=True)
    last_loss = None
    for _ in range(epochs):
        for xb, yb in loader:
            opt.zero_grad()
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            opt.step()
            last_loss = float(loss.detach().cpu())
    bundle = {
        "backend": "torch",
        "state_dict": {k: v.detach().cpu() for k, v in model.state_dict().items()},
        "n_features": X.shape[-1],
        "seq_len": SEQ_LEN,
        "last_loss": last_loss,
    }
    meta.update({"backend": "torch", "last_loss": last_loss})
    model_registry.save_artifact(org_id, TFT_MODEL_NAME, bundle, meta)
    return {**meta, "trained": True}


def score_sequences(rows, org_id: str | None = None) -> dict[str, float]:
    """Return mapping transaction_id -> temporal anomaly probability."""
    frame = transactions_to_frame(rows)
    X, ids, _ = build_vendor_sequences(frame)
    if len(ids) == 0:
        return {}
    bundle = model_registry.load_artifact(org_id, TFT_MODEL_NAME) or {"backend": "numpy"}
    torch, nn = _try_torch()
    if bundle.get("backend") == "torch" and torch is not None and bundle.get("state_dict"):
        try:
            model = _build_torch_model(nn, n_features=int(bundle.get("n_features") or X.shape[-1]))
            model.load_state_dict(bundle["state_dict"])
            model.eval()
            with torch.no_grad():
                pred = model(torch.tensor(X, dtype=torch.float32)).cpu().numpy()
            return {tid: float(np.clip(p, 0.0, 1.0)) for tid, p in zip(ids, pred)}
        except Exception as exc:
            logger.debug("Torch TFT score failed, using numpy: %s", exc)
    scores = _numpy_sequence_scores(X)
    return {tid: float(s) for tid, s in zip(ids, scores)}


def vendor_sequence_summary(rows) -> list[dict[str, Any]]:
    """Compact diagnostics for UI / working papers."""
    frame = transactions_to_frame(rows)
    scores = score_sequences(rows)
    if frame.empty:
        return []
    grouped = defaultdict(list)
    for _, row in frame.iterrows():
        grouped[str(row.get("vendor_gstin") or "")].append(str(row.get("id")))
    out = []
    for vendor, tids in grouped.items():
        vals = [scores.get(t, 0.5) for t in tids]
        out.append({
            "vendor_gstin": vendor,
            "txn_count": len(tids),
            "max_temporal_risk": round(max(vals) if vals else 0.0, 4),
            "mean_temporal_risk": round(float(np.mean(vals)) if vals else 0.0, 4),
        })
    return sorted(out, key=lambda r: -r["max_temporal_risk"])[:20]
