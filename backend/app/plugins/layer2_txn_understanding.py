"""Layer-2 transaction understanding plugin (LLM + multimodal encoding)."""

from __future__ import annotations

import io
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from typing import Any

import numpy as np
import requests
from pydantic import BaseModel, Field
from pypdf import PdfReader

logger = logging.getLogger("banking_compliance.layer2")

PROMPT_TEMPLATE = (
    "You are a CA. Given this txn data, list 5 anomalies and evidence. Return JSON "
    'with keys: anomalies (array of {{anomaly, evidence, severity}}), summary, confidence.'
)


class TransactionUnderstandingInput(BaseModel):
    txn_id: str
    tabular: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    text_narration: str = ""
    pdf_invoice_bytes: bytes | None = None


class TransactionUnderstandingOutput(BaseModel):
    embedding: list[float]
    anomaly_score: float = Field(ge=0.0, le=1.0)
    evidence_list: list[str] = Field(default_factory=list)


@dataclass
class LLMClientConfig:
    model_name: str = "llama-3.1-70b-instruct"
    base_url: str = "http://localhost:8000/v1"
    api_key: str = "EMPTY"
    timeout_seconds: int = 90
    max_batch_size: int = 8
    temperature: float = 0.1
    max_tokens: int = 700
    gpu_memory_utilization: float = 0.92
    max_model_len: int = 8192


class LLMClient:
    """vLLM OpenAI-compatible client wrapper for Llama-3.1-70B on-prem."""

    def __init__(self, config: LLMClientConfig | None = None):
        self.config = config or LLMClientConfig()
        self._session = requests.Session()

    def analyze(self, prompt_payload: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.config.model_name,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "You are a strict banking compliance assistant."},
                {"role": "user", "content": f"{PROMPT_TEMPLATE}\n\n{json.dumps(prompt_payload, default=str)}"},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        response = self._session.post(
            f"{self.config.base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        return self._safe_json(content)

    def analyze_batch(self, prompt_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        step = max(1, self.config.max_batch_size)
        for i in range(0, len(prompt_payloads), step):
            batch = prompt_payloads[i : i + step]
            for item in batch:
                out.append(self.analyze(item))
        return out

    @staticmethod
    def _safe_json(raw: str) -> dict[str, Any]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Handle responses wrapped in markdown code blocks.
            stripped = raw.strip()
            stripped = re.sub(r"^```(?:json)?", "", stripped)
            stripped = re.sub(r"```$", "", stripped).strip()
            return json.loads(stripped)


class MultiModalEncoder:
    """Encodes tabular + narration + invoice PDF into joint transaction embedding."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        embedding_dim: int = 256,
        layoutlm_model: Any | None = None,
        layoutlm_tokenizer: Any | None = None,
    ):
        self.llm_client = llm_client or LLMClient()
        self.embedding_dim = embedding_dim
        self._layoutlm_model = layoutlm_model
        self._layoutlm_tokenizer = layoutlm_tokenizer
        self._layoutlm_loaded = False

    def encode_txn(self, txn: dict[str, Any] | TransactionUnderstandingInput) -> dict[str, Any]:
        tx = txn if isinstance(txn, TransactionUnderstandingInput) else TransactionUnderstandingInput.model_validate(txn)
        pdf_fields = self._extract_pdf_fields(tx.pdf_invoice_bytes)
        tab_vec = self._tabular_vector(tx.tabular)
        text_vec = self._text_vector(tx.text_narration)
        pdf_vec = self._pdf_layout_vector(pdf_fields.get("raw_text", ""))
        embedding = self._fuse_vectors([tab_vec, text_vec, pdf_vec])

        llm_payload = {
            "txn_id": tx.txn_id,
            "tabular": tx.tabular,
            "text_narration": tx.text_narration,
            "pdf_fields": pdf_fields,
        }
        llm_out = self.llm_client.analyze(llm_payload)
        evidence_list = self._extract_evidence(llm_out)
        anomaly_score = self._anomaly_score(llm_out, evidence_list)
        result = TransactionUnderstandingOutput(
            embedding=embedding.tolist(),
            anomaly_score=anomaly_score,
            evidence_list=evidence_list,
        )
        return result.model_dump()

    def encode_batch(self, txns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Batch entrypoint with optimized LLM batching."""
        normalized = [TransactionUnderstandingInput.model_validate(t) for t in txns]
        prompt_payloads = []
        precomputed = []
        for tx in normalized:
            pdf_fields = self._extract_pdf_fields(tx.pdf_invoice_bytes)
            tab_vec = self._tabular_vector(tx.tabular)
            text_vec = self._text_vector(tx.text_narration)
            pdf_vec = self._pdf_layout_vector(pdf_fields.get("raw_text", ""))
            precomputed.append((tx, pdf_fields, self._fuse_vectors([tab_vec, text_vec, pdf_vec])))
            prompt_payloads.append(
                {
                    "txn_id": tx.txn_id,
                    "tabular": tx.tabular,
                    "text_narration": tx.text_narration,
                    "pdf_fields": pdf_fields,
                }
            )

        llm_results = self.llm_client.analyze_batch(prompt_payloads)
        outputs: list[dict[str, Any]] = []
        for (_, _, embedding), llm_out in zip(precomputed, llm_results):
            evidence_list = self._extract_evidence(llm_out)
            outputs.append(
                TransactionUnderstandingOutput(
                    embedding=embedding.tolist(),
                    anomaly_score=self._anomaly_score(llm_out, evidence_list),
                    evidence_list=evidence_list,
                ).model_dump()
            )
        return outputs

    def _extract_pdf_fields(self, pdf_bytes: bytes | None) -> dict[str, Any]:
        if not pdf_bytes:
            return {"raw_text": "", "invoice_number": None, "gstin": None, "invoice_total": None, "invoice_date": None}

        text_parts: list[str] = []
        reader = PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")
        raw_text = "\n".join(text_parts)

        invoice_no = self._search(raw_text, r"(?:invoice\s*(?:no|number)\s*[:\-]?\s*)([A-Z0-9\-/]+)")
        gstin = self._search(raw_text, r"([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9])")
        invoice_total = self._search(raw_text, r"(?:total|invoice\s*value)\s*[:\-]?\s*₹?\s*([0-9,]+(?:\.[0-9]{1,2})?)")
        invoice_date = self._search(raw_text, r"(?:date)\s*[:\-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})")
        return {
            "raw_text": raw_text[:12000],
            "invoice_number": invoice_no,
            "gstin": gstin,
            "invoice_total": invoice_total,
            "invoice_date": invoice_date,
        }

    @staticmethod
    def _search(text: str, pattern: str) -> str | None:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        return match.group(1).strip() if match else None

    def _tabular_vector(self, tabular: dict[str, Any]) -> np.ndarray:
        keys = sorted(tabular.keys())
        vec = np.zeros(self.embedding_dim, dtype=np.float32)
        for idx, key in enumerate(keys):
            value = tabular[key]
            if isinstance(value, bool):
                scalar = 1.0 if value else 0.0
            elif isinstance(value, (int, float)):
                scalar = float(value)
            elif value is None:
                scalar = 0.0
            else:
                scalar = float(len(str(value)))
            slot = idx % self.embedding_dim
            vec[slot] += math.tanh(scalar / 100000.0)
        return vec

    def _text_vector(self, text_narration: str) -> np.ndarray:
        vec = np.zeros(self.embedding_dim, dtype=np.float32)
        for i, token in enumerate(re.findall(r"[A-Za-z0-9]+", text_narration.lower())):
            slot = (hash(token) + i) % self.embedding_dim
            vec[slot] += 0.25
        return np.clip(vec, -4.0, 4.0)

    def _pdf_layout_vector(self, pdf_text: str) -> np.ndarray:
        self._ensure_layoutlm()
        if self._layoutlm_model is None or self._layoutlm_tokenizer is None:
            return self._text_vector(pdf_text)

        try:
            import torch
        except Exception:
            return self._text_vector(pdf_text)

        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._layoutlm_model.to(device)
        try:
            encoded = self._layoutlm_tokenizer(
                pdf_text[:4000],
                return_tensors="pt",
                truncation=True,
                max_length=512,
            )
        except Exception:
            return self._text_vector(pdf_text)
        encoded = {k: v.to(device) for k, v in encoded.items()}
        with torch.inference_mode():
            if device == "cuda":
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    outputs = self._layoutlm_model(**encoded)
            else:
                outputs = self._layoutlm_model(**encoded)
        pooled = outputs.last_hidden_state.mean(dim=1).detach().cpu().numpy().reshape(-1)
        if pooled.size >= self.embedding_dim:
            return pooled[: self.embedding_dim].astype(np.float32)
        out = np.zeros(self.embedding_dim, dtype=np.float32)
        out[: pooled.size] = pooled.astype(np.float32)
        return out

    def _ensure_layoutlm(self) -> None:
        if self._layoutlm_loaded:
            return
        self._layoutlm_loaded = True
        if self._layoutlm_model is not None and self._layoutlm_tokenizer is not None:
            return
        try:
            from transformers import LayoutLMv3Model, LayoutLMv3TokenizerFast

            model_name = os.getenv("LAYER2_LAYOUTLM_MODEL", "microsoft/layoutlmv3-base")
            self._layoutlm_tokenizer = LayoutLMv3TokenizerFast.from_pretrained(model_name)
            self._layoutlm_model = LayoutLMv3Model.from_pretrained(model_name)
            self._layoutlm_model.eval()
        except Exception as exc:
            logger.warning("LayoutLMv3 not available, falling back to text hashing: %s", exc)
            self._layoutlm_model = None
            self._layoutlm_tokenizer = None

    def _fuse_vectors(self, vectors: list[np.ndarray]) -> np.ndarray:
        fused = np.zeros(self.embedding_dim, dtype=np.float32)
        for vec in vectors:
            fused += vec
        norm = np.linalg.norm(fused) + 1e-8
        return fused / norm

    @staticmethod
    def _extract_evidence(llm_output: dict[str, Any]) -> list[str]:
        anomalies = llm_output.get("anomalies") or []
        evidence_list = []
        for item in anomalies:
            evidence = item.get("evidence") if isinstance(item, dict) else None
            if evidence:
                evidence_list.append(str(evidence))
        return evidence_list[:10]

    @staticmethod
    def _anomaly_score(llm_output: dict[str, Any], evidence_list: list[str]) -> float:
        anomalies = llm_output.get("anomalies") or []
        severity_map = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}
        if not anomalies:
            return 0.0
        sev = []
        for item in anomalies:
            if isinstance(item, dict):
                sev.append(severity_map.get(str(item.get("severity", "medium")).lower(), 0.5))
            else:
                sev.append(0.5)
        base = float(np.mean(sev))
        evidence_bonus = min(0.2, len(evidence_list) * 0.03)
        confidence = llm_output.get("confidence")
        if isinstance(confidence, (int, float)):
            conf = max(0.0, min(1.0, float(confidence)))
        else:
            conf = 0.6
        score = (0.65 * base) + (0.25 * conf) + evidence_bonus
        return max(0.0, min(1.0, round(score, 4)))


_default_encoder: MultiModalEncoder | None = None


def encode_txn(txn: dict[str, Any]) -> dict[str, Any]:
    """Required convenience entrypoint: encode one transaction payload."""
    global _default_encoder
    if _default_encoder is None:
        _default_encoder = MultiModalEncoder()
    return _default_encoder.encode_txn(txn)
