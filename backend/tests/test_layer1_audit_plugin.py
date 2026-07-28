from datetime import UTC, datetime
from pathlib import Path

from app.plugins.layer1_audit_engine import (
    KnowledgeGraph,
    Layer1AuditPlugin,
    RuleEngine,
    TransactionModel,
)


RULES_FILE = Path(__file__).resolve().parents[1] / "app" / "plugins" / "rules" / "rbi_pmla_layer1_rules.json"


def _base_txn() -> dict:
    return {
        "txn_id": "txn-001",
        "account_id": "ACC-1001",
        "amount": 1250000.0,
        "timestamp": datetime(2026, 7, 25, 10, 30, tzinfo=UTC),  # Saturday
        "pan": "ABCDE1234F",
        "gstin": "27ABCDE1234F1Z5",
        "device_id": "DEV-01",
        "beneficiary_account": "ACC-2002",
        "is_new_beneficiary": True,
        "days_since_beneficiary_added": 1,
        "txn_count_24h": 4,
        "total_amount_24h": 1400000.0,
        "txn_count_1h": 6,
        "total_amount_1h": 750000.0,
        "days_since_last_txn": 120,
        "is_round_amount": True,
        "is_international": True,
        "pan_gstin_mismatch": True,
        "device_change_24h": 3,
    }


def test_rule_engine_loads_json_rules() -> None:
    engine = RuleEngine.from_json_file(RULES_FILE)
    assert len(engine.rules) == 10
    assert engine.rules[0].rule_id == "rbi_ctr_over_10l"


def test_extreme_transaction_hits_many_rules_with_proofs() -> None:
    engine = RuleEngine.from_json_file(RULES_FILE)
    txn = TransactionModel.model_validate(_base_txn())
    outcomes = engine.evaluate(txn)
    hits = [rule_id for rule_id, result in outcomes.items() if result.hit]
    # CTR and structuring are mutually exclusive in this sample rule set.
    assert len(hits) >= 8
    for rule_id, result in outcomes.items():
        assert "z3_check=sat" in result.formal_proof
        assert rule_id in result.formal_proof


def test_each_sample_rule_can_be_triggered() -> None:
    engine = RuleEngine.from_json_file(RULES_FILE)
    scenarios = [
        ("rbi_ctr_over_10l", {}),
        ("pmla_structuring_24h", {"amount": 500000.0}),
        ("rbi_weekend_high_value", {}),
        ("rbi_new_beneficiary_high_value", {}),
        ("rbi_device_change_risk", {}),
        ("pmla_dormant_reactivation", {}),
        ("rbi_high_velocity_1h", {}),
        ("pmla_round_amount_pattern", {}),
        ("rbi_cross_border_new_beneficiary", {}),
        ("pmla_pan_gstin_mismatch", {}),
    ]
    for rule_id, override in scenarios:
        txn = _base_txn()
        txn.update(override)
        outcome = engine.evaluate(TransactionModel.model_validate(txn))[rule_id]
        assert outcome.hit is True
        assert "z3_check=sat" in outcome.formal_proof


def test_rules_not_hit_return_unsat_proofs() -> None:
    engine = RuleEngine.from_json_file(RULES_FILE)
    txn = _base_txn()
    txn.update(
        {
            "amount": 5000.0,
            "timestamp": datetime(2026, 7, 24, 11, 0, tzinfo=UTC),  # Friday
            "is_new_beneficiary": False,
            "txn_count_24h": 1,
            "total_amount_24h": 5000.0,
            "txn_count_1h": 1,
            "total_amount_1h": 5000.0,
            "days_since_last_txn": 2,
            "is_round_amount": False,
            "is_international": False,
            "pan_gstin_mismatch": False,
            "device_change_24h": 0,
        }
    )
    outcomes = engine.evaluate(TransactionModel.model_validate(txn))
    assert all(not result.hit for result in outcomes.values())
    assert all("z3_check=sat" in result.formal_proof for result in outcomes.values())


def test_knowledge_graph_links_account_pan_gstin_device() -> None:
    graph = KnowledgeGraph()
    graph.add_transaction(TransactionModel.model_validate(_base_txn()))

    account = "account:ACC-1001"
    pan = "pan:ABCDE1234F"
    gstin = "gstin:27ABCDE1234F1Z5"
    device = "device:DEV-01"
    beneficiary = "account:ACC-2002"

    assert graph.graph.has_node(account)
    assert graph.graph.has_node(pan)
    assert graph.graph.has_node(gstin)
    assert graph.graph.has_node(device)
    assert graph.graph.has_node(beneficiary)

    edge_relations = [data["relation"] for _, _, data in graph.graph.edges(data=True)]
    assert "has_pan" in edge_relations
    assert "has_gstin" in edge_relations
    assert "used_by" in edge_relations
    assert "transfers_to" in edge_relations


def test_plugin_audit_txn_contract() -> None:
    plugin = Layer1AuditPlugin(rule_engine=RuleEngine.from_json_file(RULES_FILE))
    result = plugin.audit_txn(_base_txn())

    assert set(result.keys()) == {"is_flagged", "rules_hit", "proof"}
    assert result["is_flagged"] is True
    assert isinstance(result["rules_hit"], list)
    assert "rbi_ctr_over_10l" in result["rules_hit"]
    assert isinstance(result["proof"], dict)
    assert "rbi_ctr_over_10l" in result["proof"]
