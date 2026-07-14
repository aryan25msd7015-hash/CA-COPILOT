"""
Gemini chat service for CA Copilot preview backend.

Powers three surfaces:
1. `/api/query/ask` — multi-turn "Ask CA Copilot" chat (gemini-2.5-flash, streaming SSE)
2. `/api/query/friday` — Friday quick-fire assistant (gemini-2.5-flash, non-streaming)
3. `/api/ai/summarize/*` — deep draft summaries for anomalies/notices/audit
   papers (gemini-2.5-pro, non-streaming)

Sessions + messages persist to MongoDB via motor. Each conversation is a
`chat_sessions` doc with a UUID; every user + assistant turn is stored in
`chat_messages` (keyed by session_id). LlmChat is instantiated fresh per
call, seeded with the stored history — this is exactly the pattern the
playbook mandates ("MAKE SURE YOU ALWAYS CREATE A NEW INSTANCE OF LlmChat
for each chat session").
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone

load_dotenv()

log = logging.getLogger("ca_platform.gemini")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

EMERGENT_LLM_KEY: str = os.environ.get("EMERGENT_LLM_KEY", "").strip()
GEMINI_CHAT_MODEL: str = os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-flash").strip()
GEMINI_FRIDAY_MODEL: str = os.environ.get("GEMINI_FRIDAY_MODEL", "gemini-2.5-flash").strip()
GEMINI_DEEP_MODEL: str = os.environ.get("GEMINI_DEEP_MODEL", "gemini-2.5-pro").strip()
MONGO_URL: str = os.environ.get("MONGO_URL", "mongodb://localhost:27017").strip()
DB_NAME: str = os.environ.get("DB_NAME", "ca_platform").strip()

# ---------------------------------------------------------------------------
# Mongo (async)
# ---------------------------------------------------------------------------

_mongo: Optional[AsyncIOMotorClient] = None


def _db():
    global _mongo
    if _mongo is None:
        _mongo = AsyncIOMotorClient(MONGO_URL, uuidRepresentation="standard")
    return _mongo[DB_NAME]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# System prompts — Command-deck operator voice (short, HUD-style, cite sections)
# ---------------------------------------------------------------------------

CA_COPILOT_SYSTEM_PROMPT = """\
You are CA Copilot — an AI operator embedded inside an Indian chartered
accountant firm's Intelligence Terminal. Your voice is a **command-deck
operator**: precise, terse, HUD-style. You cite the exact section of the
relevant Act (Income Tax, GST, Companies Act, MSME Act, Ind AS) whenever
you reference a rule.

Rules of engagement
-------------------
1. Answer in **crisp paragraphs**. No fluffy filler. If the answer is a
   number or a date, lead with it.
2. **Cite sections** when you invoke a rule: e.g. "Section 44AB of the
   Income Tax Act, 1961", "Section 16(4) of the CGST Act, 2017".
3. Prefer **bullet lists** when there are ≥3 steps or ≥3 items.
4. When the user asks for an action, respond with:
   - **SIGNAL:** one-line diagnostic (what's happening)
   - **ACTION:** the recommended next step
   - **EVIDENCE:** section / date / amount / doc reference
5. **Never invent** GSTINs, PANs, TANs, invoice numbers, or amounts. If
   you don't have the data, say "Data not in current signal — pull from
   [module]".
6. This is a **read-only advisory workspace**. Do not draft filings; draft
   summaries + suggested next moves for a human CA to review.
7. Assume the user is a CA partner or manager. Use technical terms
   directly (ITC, GSTR-2B, TDS, 43B(h), Ind AS 116, DIN, MCA).
8. If asked something outside CA / tax / audit / MCA / finance domain,
   deflect politely: "Outside my mission scope — I'm the CA Copilot."

Format all monetary amounts as INR (₹) with lakh/crore grouping where
natural. Format all dates as DD Mon YYYY (e.g. 15 Aug 2026).
"""

FRIDAY_SYSTEM_PROMPT = """\
You are **CA-Friday** — a quick-fire voice assistant embedded in a CA
firm's Intelligence Terminal. You respond to short spoken/typed commands
with **one or two crisp sentences**. Think of yourself as an air-traffic
controller: acknowledge → deliver → hand off.

Rules
-----
1. Keep every response **under 40 words**. No preamble.
2. Voice-first: use plain English, no markdown, no bullets.
3. If the user asks for a summary/brief/status, give a **one-liner** with
   numbers baked in.
4. If you don't have the data, say so and suggest which module to check.
5. Personality: calm, mission-focused, mildly futuristic.

Style examples:
- "GSTR-2B mismatches: 14 clients, ₹42 lakh at risk. Priority: Aurora
  Textiles — mismatch of ₹8.2 lakh. Opening anomalies deck."
- "Three deadlines in the next 72 hours: two GSTR-3B, one ROC AOC-4.
  Aurora Textiles is the tightest — 41 hours left."
"""

DEEP_ANALYST_SYSTEM_PROMPT = """\
You are the **CA Copilot Deep Analyst** — reviewing a single artifact
(anomaly, notice, or audit working paper) and drafting a structured
analyst summary for a human CA to review. Your output is used inside the
firm's Intelligence Terminal.

Output format (strict)
----------------------
Return your analysis in **exactly** this structure with these headings:

**SIGNAL** — one crisp paragraph: what the artifact is showing, in
plain English but with technical accuracy.

**RISK ASSESSMENT** — a bulleted list of 3-5 specific risks, each with
severity (HIGH / MEDIUM / LOW) and the exposure in ₹ if quantifiable.

**RECOMMENDED ACTIONS** — a numbered list of concrete next steps, each
with a suggested owner (Partner / Manager / Article / Client) and an
SLA (e.g. "within 48 hours").

**REGULATORY REFERENCES** — bullet list of specific Act sections and
circular numbers that apply.

**DRAFT MESSAGE** — a 2-3 sentence draft the CA can copy-paste into a
notice reply / client email (only include if the artifact type warrants
a reply; otherwise write "N/A — internal note only").

Rules
-----
1. Never fabricate GSTINs, PANs, amounts, or dates.
2. If data is thin, say "Insufficient signal — request [X] before
   drafting". Do not pad.
3. Format all amounts as INR (₹) with lakh/crore grouping.
4. Format all dates as DD Mon YYYY.
5. Assume the reader is a CA partner. Use domain terminology directly.
"""


# ---------------------------------------------------------------------------
# Session + message persistence
# ---------------------------------------------------------------------------


async def ensure_indexes() -> None:
    """Create the small set of indexes we need. Idempotent."""
    db = _db()
    try:
        await db.chat_sessions.create_index("id", unique=True)
        await db.chat_sessions.create_index([("org_id", 1), ("updated_at", -1)])
        await db.chat_messages.create_index("session_id")
        await db.chat_messages.create_index([("session_id", 1), ("created_at", 1)])
    except Exception:
        log.exception("ensure_indexes failed")


async def create_session(
    *,
    org_id: str,
    user_id: str,
    surface: str = "chat",
    title: str = "New chat",
    model: str = GEMINI_CHAT_MODEL,
) -> Dict[str, Any]:
    doc = {
        "id": f"chat-{uuid.uuid4().hex[:16]}",
        "org_id": org_id,
        "user_id": user_id,
        "surface": surface,           # "chat" | "friday" | "deep"
        "title": title,
        "model": model,
        "provider": "gemini",
        "message_count": 0,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await _db().chat_sessions.insert_one(doc)
    # Never return ObjectId to the client
    doc.pop("_id", None)
    return doc


async def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    doc = await _db().chat_sessions.find_one({"id": session_id}, {"_id": 0})
    return doc


async def list_sessions(org_id: str, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    cursor = _db().chat_sessions.find(
        {"org_id": org_id, "user_id": user_id, "surface": "chat"},
        {"_id": 0},
    ).sort("updated_at", -1).limit(limit)
    return [d async for d in cursor]


async def delete_session(session_id: str, user_id: str) -> bool:
    result = await _db().chat_sessions.delete_one({"id": session_id, "user_id": user_id})
    if result.deleted_count > 0:
        await _db().chat_messages.delete_many({"session_id": session_id})
        return True
    return False


async def add_message(session_id: str, role: str, content: str) -> Dict[str, Any]:
    """Persist a single message + bump session counters."""
    doc = {
        "id": f"msg-{uuid.uuid4().hex[:16]}",
        "session_id": session_id,
        "role": role,             # "user" | "assistant"
        "content": content,
        "created_at": _now(),
    }
    await _db().chat_messages.insert_one(doc)
    await _db().chat_sessions.update_one(
        {"id": session_id},
        {"$inc": {"message_count": 1}, "$set": {"updated_at": _now()}},
    )
    doc.pop("_id", None)
    return doc


async def get_messages(session_id: str) -> List[Dict[str, Any]]:
    cursor = _db().chat_messages.find({"session_id": session_id}, {"_id": 0}).sort("created_at", 1)
    return [d async for d in cursor]


async def rename_session_if_default(session_id: str, first_user_message: str) -> None:
    """Auto-title a session from the first user turn, if still 'New chat'."""
    title = first_user_message.strip()
    if len(title) > 60:
        title = title[:57] + "…"
    await _db().chat_sessions.update_one(
        {"id": session_id, "title": "New chat"},
        {"$set": {"title": title or "New chat"}},
    )


# ---------------------------------------------------------------------------
# Chat factory — creates a fresh LlmChat seeded with prior history
# ---------------------------------------------------------------------------


def _build_chat(
    *,
    session_id: str,
    system_prompt: str,
    model: str,
) -> LlmChat:
    if not EMERGENT_LLM_KEY:
        raise RuntimeError(
            "EMERGENT_LLM_KEY is not set. Add it to backend/.env and restart backend."
        )
    return LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=system_prompt,
    ).with_model("gemini", model)


async def _seed_history(chat: LlmChat, session_id: str) -> None:
    """Replay stored history into the LlmChat so context is preserved
    across process restarts. LlmChat has an internal message list — the
    playbook stores conversation state per-instance, so on a cold start we
    need to feed prior messages back in."""
    history = await get_messages(session_id)
    # LlmChat exposes an internal `messages` list we can pre-populate. Use
    # the same shape emergentintegrations expects.
    for m in history:
        try:
            chat.messages.append({"role": m["role"], "content": m["content"]})
        except Exception:  # pragma: no cover - defensive
            pass


# ---------------------------------------------------------------------------
# Public API — streaming chat
# ---------------------------------------------------------------------------


async def stream_chat(session_id: str, user_text: str) -> AsyncIterator[str]:
    """Yield text deltas from Gemini for a persisted chat session.

    Persists both the user turn (before sending) and the assistant turn
    (after StreamDone). Rename session from 'New chat' on first turn.
    """
    session = await get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    await add_message(session_id, "user", user_text)
    await rename_session_if_default(session_id, user_text)

    chat = _build_chat(
        session_id=session_id,
        system_prompt=CA_COPILOT_SYSTEM_PROMPT,
        model=session.get("model") or GEMINI_CHAT_MODEL,
    )
    await _seed_history(chat, session_id)

    buffer: List[str] = []
    try:
        async for ev in chat.stream_message(UserMessage(text=user_text)):
            if isinstance(ev, TextDelta):
                buffer.append(ev.content)
                yield ev.content
            elif isinstance(ev, StreamDone):
                break
    finally:
        assistant_text = "".join(buffer)
        if assistant_text:
            await add_message(session_id, "assistant", assistant_text)


# ---------------------------------------------------------------------------
# Public API — non-streaming (Friday + deep analyst)
# ---------------------------------------------------------------------------


async def friday_answer(user_text: str, context: Optional[str] = None) -> str:
    """Fire-and-forget one-shot for the Friday widget."""
    session_id = f"friday-{uuid.uuid4().hex[:12]}"
    system = FRIDAY_SYSTEM_PROMPT
    if context:
        system = f"{system}\n\nCurrent workspace context:\n{context}"
    chat = _build_chat(
        session_id=session_id,
        system_prompt=system,
        model=GEMINI_FRIDAY_MODEL,
    )
    reply = await chat.send_message(UserMessage(text=user_text))
    return (reply or "").strip()


async def deep_analyst(*, artifact_type: str, artifact: Dict[str, Any]) -> str:
    """Deep summary of an anomaly / notice / audit-paper artifact."""
    session_id = f"deep-{uuid.uuid4().hex[:12]}"
    chat = _build_chat(
        session_id=session_id,
        system_prompt=DEEP_ANALYST_SYSTEM_PROMPT,
        model=GEMINI_DEEP_MODEL,
    )
    # Format the artifact as a clean prompt block
    lines = [f"ARTIFACT TYPE: {artifact_type.upper()}", ""]
    for k, v in artifact.items():
        lines.append(f"{k}: {v}")
    prompt = "\n".join(lines) + "\n\nDraft the structured summary now."
    reply = await chat.send_message(UserMessage(text=prompt))
    return (reply or "").strip()


# ---------------------------------------------------------------------------
# Starter prompts for the /query page
# ---------------------------------------------------------------------------

STARTER_PROMPTS: List[Dict[str, Any]] = [
    {"category": "Compliance",  "intent": "gst_next72",
     "prompt": "Which clients have GST filings due in the next 72 hours and what's their readiness?",
     "recommended": True},
    {"category": "Compliance",  "intent": "gstr2b_mismatch",
     "prompt": "Summarise this month's GSTR-2B mismatches by client — highlight anything above ₹5 lakh.",
     "recommended": True},
    {"category": "Risk",        "intent": "high_risk_clients",
     "prompt": "List my top 5 highest-risk clients by health score and explain what's dragging each score down.",
     "recommended": False},
    {"category": "Risk",        "intent": "msme_43b_exposure",
     "prompt": "What's my total MSME 43B(h) disallowance exposure across the portfolio, and which clients need action first?",
     "recommended": True},
    {"category": "Practice",    "intent": "workload_imbalance",
     "prompt": "Is my team's workload balanced right now? Who is overloaded and who has capacity?",
     "recommended": False},
    {"category": "Practice",    "intent": "billing_at_risk",
     "prompt": "Which invoices are more than 15 days overdue and what's the total collection gap?",
     "recommended": False},
    {"category": "Advisory",    "intent": "explain_43bh",
     "prompt": "Explain Section 43B(h) of the Income Tax Act in a 3-bullet summary I can share with a manufacturing client.",
     "recommended": False},
    {"category": "Advisory",    "intent": "gstr9_checklist",
     "prompt": "Give me a pre-filing checklist for GSTR-9 for a client with turnover above ₹5 crore.",
     "recommended": False},
]


__all__ = [
    "EMERGENT_LLM_KEY",
    "GEMINI_CHAT_MODEL",
    "GEMINI_FRIDAY_MODEL",
    "GEMINI_DEEP_MODEL",
    "CA_COPILOT_SYSTEM_PROMPT",
    "FRIDAY_SYSTEM_PROMPT",
    "DEEP_ANALYST_SYSTEM_PROMPT",
    "STARTER_PROMPTS",
    "ensure_indexes",
    "create_session",
    "get_session",
    "list_sessions",
    "delete_session",
    "add_message",
    "get_messages",
    "stream_chat",
    "friday_answer",
    "deep_analyst",
]
