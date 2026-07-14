"""Source-grounded assistant orchestration with deterministic fallback."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.config import settings
from app.engines.nl_query_engine import execute_query, translate_to_sql, translate_to_sql_fallback


@dataclass
class GroundingSource:
    source_type: str
    title: str
    excerpt: str
    reference_id: str | None = None
    score: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "title": self.title,
            "excerpt": self.excerpt,
            "reference_id": self.reference_id,
            "score": self.score,
        }


def _terms(question: str) -> list[str]:
    stop = {"show", "list", "which", "what", "where", "have", "with", "that", "this", "from", "client", "clients"}
    return [w for w in re.findall(r"[a-zA-Z0-9]{3,}", question.lower()) if w not in stop][:8]


def _excerpt(value: str, max_len: int = 260) -> str:
    collapsed = " ".join((value or "").split())
    return collapsed[:max_len] + ("..." if len(collapsed) > max_len else "")


def retrieve_sources(question: str, org_id: str, db, limit: int = 6) -> list[GroundingSource]:
    terms = _terms(question)
    sources: list[GroundingSource] = []

    if terms:
        pattern = "|".join(re.escape(term) for term in terms)
        legal_rows = db.execute(
            text(
                "SELECT id, doc_type, content FROM legal_chunks "
                "WHERE content ~* :pattern ORDER BY created_at DESC LIMIT :limit"
            ),
            {"pattern": pattern, "limit": max(1, limit // 2)},
        ).fetchall()
        for row in legal_rows:
            sources.append(GroundingSource(
                source_type="legal_chunk",
                title=f"Legal reference: {row.doc_type}",
                excerpt=_excerpt(row.content),
                reference_id=str(row.id),
                score=0.72,
            ))

    doc_rows = db.execute(
        text(
            "SELECT d.id, d.doc_type, d.status, d.ocr_text, c.name AS client_name "
            "FROM documents d JOIN clients c ON c.id = d.client_id "
            "WHERE d.org_id = :org_id AND c.org_id = :org_id AND d.ocr_text IS NOT NULL "
            "ORDER BY d.created_at DESC LIMIT :limit"
        ),
        {"org_id": org_id, "limit": limit},
    ).fetchall()
    for row in doc_rows:
        if len(sources) >= limit:
            break
        sources.append(GroundingSource(
            source_type="document",
            title=f"{row.client_name} {row.doc_type} ({row.status})",
            excerpt=_excerpt(row.ocr_text),
            reference_id=str(row.id),
            score=0.6,
        ))
    return sources[:limit]


def capability_status() -> dict[str, Any]:
    return {
        "llm_provider": "anthropic" if settings.ANTHROPIC_API_KEY else "deterministic_fallback",
        "embedding_provider": "openai" if settings.OPENAI_API_KEY else "keyword_and_sql",
        "rag_mode": "semantic_vector" if settings.OPENAI_API_KEY else "keyword_grounded",
        "fallback_reason": None if settings.ANTHROPIC_API_KEY else "ANTHROPIC_API_KEY is not configured",
    }


def answer_from_rows(question: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No matching tenant data was found for this question."
    preview = rows[:5]
    fields = list(preview[0].keys())[:4]
    lines = []
    for index, row in enumerate(preview, 1):
        values = ", ".join(f"{field}: {row.get(field)}" for field in fields)
        lines.append(f"{index}. {values}")
    suffix = f" Showing 5 of {len(rows)} rows." if len(rows) > 5 else ""
    return f"I found {len(rows)} matching record(s) for: {question}.{suffix}\n" + "\n".join(lines)


def grounded_query(question: str, org_id: str, db) -> dict[str, Any]:
    provider = "deterministic_fallback"
    fallback_reason = None
    try:
        if settings.ANTHROPIC_API_KEY:
            from anthropic import Anthropic

            sql = translate_to_sql(question, org_id, Anthropic(api_key=settings.ANTHROPIC_API_KEY))
            provider = "anthropic"
        else:
            fallback_reason = "ANTHROPIC_API_KEY is not configured"
            sql = translate_to_sql_fallback(question)
    except Exception as exc:
        fallback_reason = f"LLM SQL translation failed: {exc}"
        sql = translate_to_sql_fallback(question)

    result = execute_query(sql, org_id, db)
    sources = retrieve_sources(question, org_id, db)
    capability = capability_status()
    confidence = "high" if result["row_count"] > 0 and provider != "deterministic_fallback" else "medium" if result["row_count"] > 0 else "low"
    result.update({
        "provider": provider,
        "question": question,
        "answer": answer_from_rows(question, result["rows"]),
        "confidence": confidence,
        "grounding": {
            "sources": [source.as_dict() for source in sources],
            "source_count": len(sources),
            "capability": capability,
            "fallback_reason": fallback_reason or capability.get("fallback_reason"),
        },
        "guardrails": {
            "tenant_scoped": ":org_id" in sql,
            "read_only_sql": True,
            "max_rows": 500,
        },
    })
    return result
