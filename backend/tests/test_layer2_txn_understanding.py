from __future__ import annotations

from typing import Any

from pypdf import PdfWriter

from app.plugins.layer2_txn_understanding import LLMClient, MultiModalEncoder


class FakeLLMClient(LLMClient):
    def __init__(self):
        pass

    def analyze(self, prompt_payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "anomalies": [
                {"anomaly": "High value outlier", "evidence": "Amount exceeds historical median by 9x", "severity": "high"},
                {"anomaly": "New beneficiary", "evidence": "Beneficiary added within 1 day", "severity": "medium"},
            ],
            "summary": "Potential layering pattern",
            "confidence": 0.88,
        }

    def analyze_batch(self, prompt_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.analyze(item) for item in prompt_payloads]


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    out = bytes()
    import io

    fp = io.BytesIO()
    writer.write(fp)
    out = fp.getvalue()
    return out


def test_encode_txn_returns_contract() -> None:
    encoder = MultiModalEncoder(llm_client=FakeLLMClient(), embedding_dim=64)
    out = encoder.encode_txn(
        {
            "txn_id": "t-1",
            "tabular": {"amount": 1250000, "txn_count_24h": 4, "is_new_beneficiary": True},
            "text_narration": "Urgent vendor payment for hardware invoice",
            "pdf_invoice_bytes": _pdf_bytes(),
        }
    )
    assert set(out.keys()) == {"embedding", "anomaly_score", "evidence_list"}
    assert len(out["embedding"]) == 64
    assert 0.0 <= out["anomaly_score"] <= 1.0
    assert len(out["evidence_list"]) >= 1


def test_encode_batch_supports_batched_inference() -> None:
    encoder = MultiModalEncoder(llm_client=FakeLLMClient(), embedding_dim=32)
    batch = [
        {
            "txn_id": "t-1",
            "tabular": {"amount": 1250000, "txn_count_24h": 4},
            "text_narration": "cash withdrawal and transfer",
        },
        {
            "txn_id": "t-2",
            "tabular": {"amount": 50000, "txn_count_24h": 1},
            "text_narration": "routine salary credit",
        },
    ]
    out = encoder.encode_batch(batch)
    assert len(out) == 2
    assert all(len(item["embedding"]) == 32 for item in out)
    assert all("evidence_list" in item for item in out)
