"""RAG-based tax notice drafter."""
import re
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

NOTICE_RE = {
    "notice_type":  re.compile(r'(Intimation|Scrutiny|Demand|Show Cause)', re.IGNORECASE),
    "section":      re.compile(r'[Uu]nder [Ss]ection\s+(\d+[A-Za-z]*(?:/\d+[A-Za-z]*)*)'),
    "ay":           re.compile(r'A\.?Y\.?\s*(20\d{2}-\d{2,4})'),
    "demand_amt":   re.compile(r'(?:Rs|INR|₹)\.?\s*([\d,]+(?:\.\d{2})?)'),
    "due_date":     re.compile(r'(?:within|by|before)\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'),
}


def build_knowledge_base(docs: list[tuple[str, str]], db) -> int:
    """Chunk and embed legal documents, returning the inserted chunk count."""
    from openai import OpenAI
    from app.config import settings
    from app.models.legal_chunk import LegalChunk

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    inserted = 0
    for doc_type, content in docs:
        words = content.split()
        for start in range(0, len(words), 350):
            chunk = " ".join(words[max(0, start - 50):start + 400]).strip()
            if not chunk:
                continue
            embedding = client.embeddings.create(
                model="text-embedding-3-small", input=chunk
            ).data[0].embedding
            db.add(LegalChunk(doc_type=doc_type, content=chunk, embedding=embedding))
            inserted += 1
    db.commit()
    return inserted


def parse_notice(text: str) -> dict:
    result = {}
    for key, pattern in NOTICE_RE.items():
        m = pattern.search(text)
        result[key] = m.group(1) if m else None
    result["summary"] = " ".join(text.split()[:80])
    return result


def retrieve_legal_context(notice_text: str, db, k: int = 5) -> list[str]:
    """Semantic search over legal_chunks using pgvector cosine similarity."""
    from app.models.legal_chunk import LegalChunk
    from openai import OpenAI
    from app.config import settings

    if not settings.OPENAI_API_KEY:
        return []

    oai = OpenAI(api_key=settings.OPENAI_API_KEY)
    emb_response = oai.embeddings.create(
        model="text-embedding-3-small", input=notice_text[:4000]
    )
    query_emb = emb_response.data[0].embedding

    # pgvector cosine distance operator: <=>
    from sqlalchemy import text
    rows = db.execute(
        text("SELECT content, 1 - (embedding <=> CAST(:q AS vector)) AS similarity "
             "FROM legal_chunks ORDER BY similarity DESC LIMIT :k"),
        {"q": str(query_emb), "k": k},
    ).fetchall()
    return [row[0] for row in rows]


def draft_reply_fallback(notice_data: dict, chunks: list[str]) -> dict:
    """Create a deterministic review draft when LLM/legal context is unavailable."""
    notice_type = notice_data.get("notice_type") or "tax notice"
    section = notice_data.get("section")
    assessment_year = notice_data.get("ay") or "the relevant assessment year"
    demand_amount = notice_data.get("demand_amt")
    due_date = notice_data.get("due_date")
    context_note = (
        "The legal context library contains supporting excerpts for review."
        if chunks else
        "CA REVIEW REQUIRED - insufficient legal basis. No verified legal context was available."
    )
    section_line = f"under Section {section}" if section else "under the section referred to in the notice"
    amount_line = f"The notice refers to a demand/amount of INR {demand_amount}." if demand_amount else "The demand amount should be verified from the notice and portal ledger."
    due_line = f"The response due date appears to be {due_date}." if due_date else "The response due date should be confirmed from the notice portal."
    draft = f"""To
The Assessing/Proper Officer

Subject: Preliminary reply to {notice_type} {section_line} for A.Y. {assessment_year}

Respected Sir/Madam,

We submit this preliminary response on behalf of the assessee. The notice has been reviewed from the available OCR text and the following points require verification before final filing:

1. {amount_line}
2. {due_line}
3. The facts, ledger extracts, return acknowledgements, challans, and supporting reconciliations should be attached after review.
4. {context_note}

Without prejudice, the assessee requests that no adverse inference be drawn until the supporting records are considered and an opportunity of hearing is granted.

This draft is generated for professional review and should not be filed without CA approval.

Yours faithfully,
Authorized Representative"""
    return {
        "draft": draft,
        "notice_data": notice_data,
        "validation": {
            "valid": False,
            "cited": [section] if section else [],
            "unverified": [section] if section else [],
            "confidence": "review_required",
            "provider": "deterministic_fallback",
        },
        "source_chunks": chunks,
        "provider": "deterministic_fallback",
    }


def draft_reply(notice_data: dict, chunks: list[str], anthropic_client) -> dict:
    """Generate a guardrailed reply draft using Claude."""
    context = "\n\n---\n\n".join(chunks)
    system = f"""You are a legal assistant for a Chartered Accountant in India.
STRICT RULES:
1. Only cite section numbers that appear verbatim in the CONTEXT below.
2. Never invent case laws, tribunal orders, or circular numbers.
3. If the context is insufficient, write exactly: "CA REVIEW REQUIRED — insufficient legal basis."
4. Use formal language suitable for Indian tax proceedings.

VERIFIED LEGAL CONTEXT:
{context}"""

    message = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=system,
        messages=[{
            "role": "user",
            "content": f"Notice details: {json.dumps(notice_data)}\n\nDraft a formal reply."
        }],
    )
    draft = message.content[0].text
    validation = validate_citations(draft, context)
    return {"draft": draft, "validation": validation, "source_chunks": chunks}


def draft_reply_openai(notice_data: dict, chunks: list[str], openai_client) -> dict:
    """Fallback draft generation using OpenAI."""
    context = "\n\n---\n\n".join(chunks)
    resp = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": f"You are a CA legal assistant. Only cite sections in CONTEXT.\n\nCONTEXT:\n{context}"},
            {"role": "user", "content": f"Notice: {json.dumps(notice_data)}\nDraft formal reply."},
        ],
        max_tokens=2000,
    )
    draft = resp.choices[0].message.content
    validation = validate_citations(draft, context)
    return {"draft": draft, "validation": validation, "source_chunks": chunks}


def validate_citations(draft: str, context: str) -> dict:
    """Check that every cited section exists in the retrieved context."""
    cited = set(re.findall(r'[Ss]ection\s+(\d+[A-Za-z]*(?:/\d+[A-Za-z]*)*)', draft))
    unverified = [s for s in cited if s not in context]
    return {
        "valid": not unverified,
        "cited": list(cited),
        "unverified": unverified,
        "confidence": "high" if not unverified else "low",
    }
