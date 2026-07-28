from datetime import UTC, datetime
from pathlib import Path

from app.v3.l1_rules.rule_engine import RuleEngine


RULES = Path(__file__).resolve().parents[1] / "app" / "v3" / "l1_rules" / "rules" / "rbi_rules_5.json"


def _txn() -> dict:
    return {
        "txn_id": "t-1",
        "amount": 1250000.0,
        "timestamp": datetime(2026, 7, 26, 11, 0, tzinfo=UTC),  # Sunday
        "txn_count_24h": 5,
        "total_amount_24h": 1700000.0,
        "is_new_beneficiary": True,
        "is_international": True,
        "pan_gstin_mismatch": True,
    }


def test_load_5_rules() -> None:
    engine = RuleEngine.from_json(RULES)
    assert len(engine.rules) == 5


def test_audit_contract_and_proof() -> None:
    engine = RuleEngine.from_json(RULES)
    result = engine.audit_txn(_txn())
    assert set(result.keys()) == {"is_flagged", "rules_hit", "proof"}
    assert result["is_flagged"] is True
    assert len(result["rules_hit"]) >= 4
    assert len(result["proof"]) == 5
    for proof in result["proof"].values():
        assert "z3_check=sat" in proof


def test_non_risky_txn_is_not_flagged() -> None:
    engine = RuleEngine.from_json(RULES)
    txn = _txn()
    txn.update(
        {
            "amount": 5000.0,
            "timestamp": datetime(2026, 7, 27, 12, 0, tzinfo=UTC),  # Monday
            "txn_count_24h": 1,
            "total_amount_24h": 5000.0,
            "is_new_beneficiary": False,
            "is_international": False,
            "pan_gstin_mismatch": False,
        }
    )
    result = engine.audit_txn(txn)
    assert result["is_flagged"] is False
    assert result["rules_hit"] == []
