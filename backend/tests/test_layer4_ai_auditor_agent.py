from app.plugins.layer4_ai_auditor_agent import Layer4AIAuditorAgent


def _sample_payload() -> dict:
    return {
        "txn_id": "txn-9001",
        "account_id": "ACCT-77X",
        "amount": 1350000.0,
        "metadata": {"gstin": "27ABCDE1234F1Z5"},
        "l1_output": {"risk_score": 0.72, "rules_hit": ["rbi_ctr_over_10l"]},
        "l2_output": {"risk_probability": 0.66},
        "l3_output": {"predicted_7d_risk": 0.71, "ring_summary": {"rings_detected": 2}},
    }


def test_investigate_returns_contract_and_evidence() -> None:
    agent = Layer4AIAuditorAgent()
    out = agent.investigate(_sample_payload())
    assert set(out.keys()) == {"final_risk", "remark", "evidence_pack"}
    assert out["final_risk"] in {"low", "medium", "high", "critical"}
    assert out["remark"]
    assert "tool_calls" in out["evidence_pack"]
    assert len(out["evidence_pack"]["tool_calls"]) >= 2
    assert isinstance(out["evidence_pack"]["composite_score"], float)


def test_tool_calls_are_logged_to_audit_trail() -> None:
    agent = Layer4AIAuditorAgent()
    agent.investigate(_sample_payload())
    assert len(agent.audit_trail) >= 2
    names = {record.tool_name for record in agent.audit_trail}
    assert "draft_remark" in names
    assert "get_account_360" in names


def test_feedback_reward_policy_matches_ca_outcome() -> None:
    agent = Layer4AIAuditorAgent()
    approved = agent.apply_ca_feedback(True)
    rejected = agent.apply_ca_feedback(False)
    assert approved["reward"] == 10.0
    assert rejected["reward"] == -5.0
    assert approved["reward_history_tail"]


def test_nightly_fraud_simulator_generates_rows() -> None:
    agent = Layer4AIAuditorAgent()
    batch = agent.run_nightly_fraud_simulation(batch_size=6)
    assert batch["batch_size"] == 6
    assert len(batch["synthetic_transactions"]) == 6
    assert all("amount" in row for row in batch["synthetic_transactions"])
