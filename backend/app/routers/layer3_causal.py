"""Layer-3 causal analysis APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.plugins.layer3_causal_engine import Layer3Engine
from app.utils.deps import require_feature

router = APIRouter()
_engine = Layer3Engine()


class Layer3AnalyzeRequest(BaseModel):
    txn: dict
    features: dict[str, float] = Field(default_factory=dict)
    history: list[dict[str, float]] = Field(default_factory=list)
    graph_edges: list[tuple[str, str, float]] = Field(default_factory=list)


@router.get("/status")
def status(_=Depends(require_feature("causal_risk_layer3"))):
    return {
        "plugin": "layer3_causal_risk",
        "status": "active",
        "world_model_sequence_length": _engine.world_model.config.sequence_length,
        "graph_nodes": _engine.graph_analyzer.graph.number_of_nodes(),
        "graph_edges": _engine.graph_analyzer.graph.number_of_edges(),
    }


@router.post("/analyze")
def analyze(payload: Layer3AnalyzeRequest, _=Depends(require_feature("causal_risk_layer3"))):
    result = _engine.analyze(
        txn=payload.txn,
        features=payload.features,
        history=payload.history,
        graph_edges=payload.graph_edges,
    )
    figure = _engine.build_risk_visualization(
        current_risk=result["current_risk"],
        predicted_7d_risk=result["predicted_7d_risk"],
        history=payload.history,
    )
    return {
        **result,
        "visualization": figure.to_plotly_json(),
    }
