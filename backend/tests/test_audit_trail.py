import json

from app.services.audit_trail import ImmutableAuditTrail


def test_immutable_audit_trail_hash_chain(tmp_path) -> None:
    trail_file = tmp_path / "audit_trail.jsonl"
    trail = ImmutableAuditTrail(trail_file)
    first = trail.write_event("audit_txn", {"investigation_id": "one"})
    second = trail.write_event("ca_feedback", {"investigation_id": "one", "approved": True})

    assert first["prev_hash"] == "GENESIS"
    assert second["prev_hash"] == first["event_hash"]

    rows = [json.loads(line) for line in trail_file.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[1]["prev_hash"] == rows[0]["event_hash"]
