from app.plugins.layer3_causal_engine import (
    AccountGraphAnalyzer,
    CausalAnalyzer,
    Layer3Engine,
    WorldModel,
)


def test_get_root_cause_returns_contract() -> None:
    analyzer = CausalAnalyzer()
    out = analyzer.get_root_cause(
        txn={"amount": 850000},
        features={"new_beneficiary": 0.9, "weekend": 0.2, "device_change": 0.4},
    )
    assert set(out.keys()) == {
        "primary_cause",
        "counterfactual_risk",
        "current_risk",
        "causal_explanation",
    }
    assert out["primary_cause"] == "new_beneficiary"
    assert 0.0 <= out["counterfactual_risk"] <= 1.0


def test_world_model_predicts_bounded_7d_risk() -> None:
    model = WorldModel()
    history = [
        {"outflow_risk": 0.2, "inflow_risk": 0.1, "concentration_risk": 0.3},
        {"outflow_risk": 0.7, "inflow_risk": 0.5, "concentration_risk": 0.8},
    ]
    risk = model.predict_7d_risk(history)
    assert 0.0 <= risk <= 1.0


def test_detect_rings_finds_simple_cycle() -> None:
    graph = AccountGraphAnalyzer()
    graph.build_graph(
        [
            ("A1", "A2", 1000.0),
            ("A2", "A3", 2000.0),
            ("A3", "A1", 3000.0),
        ]
    )
    result = graph.detect_rings("A1")
    assert result["rings_detected"] >= 1
    assert any("A1" in cycle for cycle in result["ring_members"])


def test_layer3_engine_outputs_required_fields() -> None:
    engine = Layer3Engine()
    out = engine.analyze(
        txn={"account_id": "A1", "amount": 850000},
        features={"new_beneficiary": 0.9, "weekend": 0.2},
        history=[
            {"outflow_risk": 0.3, "inflow_risk": 0.2, "concentration_risk": 0.4},
            {"outflow_risk": 0.6, "inflow_risk": 0.4, "concentration_risk": 0.7},
        ],
        graph_edges=[("A1", "A2", 1000.0), ("A2", "A3", 2000.0), ("A3", "A1", 1500.0)],
    )
    assert set(out.keys()) == {"current_risk", "predicted_7d_risk", "causal_explanation"}
    assert 0.0 <= out["current_risk"] <= 1.0
    assert 0.0 <= out["predicted_7d_risk"] <= 1.0


def test_plotly_visualization_builds() -> None:
    engine = Layer3Engine()
    fig = engine.build_risk_visualization(
        current_risk=0.72,
        predicted_7d_risk=0.84,
        history=[
            {"outflow_risk": 0.2},
            {"outflow_risk": 0.3},
            {"outflow_risk": 0.55},
        ],
    )
    assert len(fig.data) == 2
