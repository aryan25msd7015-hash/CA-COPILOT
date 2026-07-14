"""
ElevenLabs TTS service for CA Copilot preview backend.

Two surfaces:
- **Friday** — snappy, low-latency (eleven_flash_v2_5)
- **Long-form read-aloud** — best-quality studio narration (eleven_multilingual_v2)

In dry-run mode (default when `ELEVENLABS_API_KEY=sk_placeholder`), we
stream back a hardcoded ~1 second silent MP3 so the frontend audio
pipeline works end-to-end. Real synthesis flips on the moment a real
key is dropped in.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("ca_platform.elevenlabs")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ELEVENLABS_API_KEY: str = os.environ.get("ELEVENLABS_API_KEY", "").strip()
_DRY_RUN_ENV: str = os.environ.get("ELEVENLABS_DRY_RUN", "false").strip().lower()
DEFAULT_VOICE_ID: str = os.environ.get(
    "ELEVENLABS_VOICE_ID", "9BWtsMINqrJLrRacOk9x"  # Aria
).strip()
FRIDAY_VOICE_ID: str = os.environ.get(
    "ELEVENLABS_FRIDAY_VOICE_ID", "Xb7hH8MSUJpSbSDYk0k2"  # Alice
).strip()
LONG_MODEL: str = os.environ.get("ELEVENLABS_LONG_MODEL", "eleven_multilingual_v2").strip()
FRIDAY_MODEL: str = os.environ.get("ELEVENLABS_FRIDAY_MODEL", "eleven_flash_v2_5").strip()

# Public preview limits
MAX_TEXT_CHARS = 4000


def is_placeholder() -> bool:
    return (not ELEVENLABS_API_KEY) or ELEVENLABS_API_KEY.startswith("sk_placeholder")


def is_dry_run() -> bool:
    if _DRY_RUN_ENV in {"1", "true", "yes", "on"}:
        return True
    return is_placeholder()


# ---------------------------------------------------------------------------
# SDK client (lazy — never instantiated in dry-run so the module imports
# cleanly even without a real key)
# ---------------------------------------------------------------------------

_client = None


def _get_client():
    global _client
    if _client is None:
        # Import lazily so dry-run mode doesn't need the SDK at all.
        from elevenlabs.client import AsyncElevenLabs

        _client = AsyncElevenLabs(api_key=ELEVENLABS_API_KEY, timeout=60.0)
    return _client


# ---------------------------------------------------------------------------
# Curated premade voice catalogue (used as fallback in dry-run + as an
# always-available default set). Voice IDs are the public premade IDs from
# ElevenLabs docs; they resolve for any account.
# ---------------------------------------------------------------------------

CURATED_VOICES: List[Dict[str, Any]] = [
    {"voice_id": "9BWtsMINqrJLrRacOk9x", "name": "Aria",
     "labels": {"accent": "American", "gender": "female", "use_case": "narration"},
     "description": "Expressive, versatile — recommended for long-form read-aloud."},
    {"voice_id": "Xb7hH8MSUJpSbSDYk0k2", "name": "Alice",
     "labels": {"accent": "British", "gender": "female", "use_case": "conversational"},
     "description": "Bright, snappy — recommended for Friday quick-fire."},
    {"voice_id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah",
     "labels": {"accent": "American", "gender": "female", "use_case": "professional"},
     "description": "Calm, professional — good for compliance briefings."},
    {"voice_id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel",
     "labels": {"accent": "American", "gender": "female", "use_case": "narration"},
     "description": "Warm, clear — classic ElevenLabs demo voice."},
    {"voice_id": "onwK4e9ZLuTAKqWW03F9", "name": "Daniel",
     "labels": {"accent": "British", "gender": "male", "use_case": "news"},
     "description": "Authoritative newsreader tone."},
    {"voice_id": "TX3LPaxmHKxFdv7VOQHJ", "name": "Liam",
     "labels": {"accent": "American", "gender": "male", "use_case": "narration"},
     "description": "Grounded, articulate — good for audit walk-throughs."},
    {"voice_id": "pFZP5JQG7iQjIQuC4Bku", "name": "Lily",
     "labels": {"accent": "British", "gender": "female", "use_case": "warm"},
     "description": "Warm, personable — client-portal invitations."},
    {"voice_id": "CwhRBWXzGAHq8TQ4Fs17", "name": "Roger",
     "labels": {"accent": "American", "gender": "male", "use_case": "confident"},
     "description": "Confident partner voice — practice-management briefings."},
]


async def list_voices() -> Dict[str, Any]:
    """Return the effective voice catalogue. In dry-run this is the curated
    list. With a real key we try to fetch the account's voices (which
    includes the curated premade + any custom-cloned voices) and fall back
    to the curated list on error."""
    if is_dry_run():
        return {
            "provider": "elevenlabs",
            "dry_run": True,
            "default_voice_id": DEFAULT_VOICE_ID,
            "friday_voice_id": FRIDAY_VOICE_ID,
            "voices": CURATED_VOICES,
        }

    try:
        client = _get_client()
        resp = await client.voices.get_all()
        # Response has `voices` list of Voice objects
        remote: List[Dict[str, Any]] = []
        for v in getattr(resp, "voices", []) or []:
            labels = getattr(v, "labels", None) or {}
            remote.append({
                "voice_id": v.voice_id,
                "name": v.name,
                "labels": labels if isinstance(labels, dict) else {},
                "description": getattr(v, "description", "") or "",
                "category": getattr(v, "category", ""),
            })
        return {
            "provider": "elevenlabs",
            "dry_run": False,
            "default_voice_id": DEFAULT_VOICE_ID,
            "friday_voice_id": FRIDAY_VOICE_ID,
            "voices": remote or CURATED_VOICES,
        }
    except Exception as exc:  # pragma: no cover — network path
        log.warning("list_voices remote fetch failed, falling back to curated: %s", exc)
        return {
            "provider": "elevenlabs",
            "dry_run": False,
            "default_voice_id": DEFAULT_VOICE_ID,
            "friday_voice_id": FRIDAY_VOICE_ID,
            "voices": CURATED_VOICES,
            "remote_error": str(exc),
        }


# ---------------------------------------------------------------------------
# Silent audio stub for dry-run (~0.5s of silence, tiny valid WAV file)
# ---------------------------------------------------------------------------

import io as _io
import wave as _wave


def _build_silent_wav(duration_s: float = 0.5, sample_rate: int = 22050) -> bytes:
    """Build a tiny valid mono 16-bit silent WAV. Any browser <audio> plays this."""
    n_samples = int(sample_rate * duration_s)
    buf = _io.BytesIO()
    with _wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_samples)
    return buf.getvalue()


_SILENT_WAV_BYTES: bytes = _build_silent_wav()
DRY_RUN_MEDIA_TYPE = "audio/wav"
REAL_MEDIA_TYPE = "audio/mpeg"


async def _dry_run_stream() -> AsyncIterator[bytes]:
    """Yield the silent stub in a couple of chunks so it feels like a stream."""
    data = _SILENT_WAV_BYTES
    mid = len(data) // 2
    yield data[:mid]
    await asyncio.sleep(0.02)
    yield data[mid:]


# ---------------------------------------------------------------------------
# TTS usage log (in-memory — mirrors the Resend email log pattern)
# ---------------------------------------------------------------------------

TTS_LOG: List[Dict[str, Any]] = []


def _log_synthesis(
    *,
    surface: str,
    voice_id: str,
    model_id: str,
    text: str,
    dry_run: bool,
    error: Optional[str] = None,
) -> None:
    TTS_LOG.insert(
        0,
        {
            "id": f"tts-{uuid.uuid4().hex[:12]}",
            "surface": surface,
            "voice_id": voice_id,
            "model_id": model_id,
            "text_preview": (text[:120] + "…") if len(text) > 120 else text,
            "chars": len(text),
            "dry_run": dry_run,
            "error": error,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    del TTS_LOG[500:]  # cap


# ---------------------------------------------------------------------------
# Streaming synth — public API
# ---------------------------------------------------------------------------


async def synthesize_stream(
    *,
    text: str,
    surface: str = "read_aloud",
    voice_id: Optional[str] = None,
    model_id: Optional[str] = None,
    stability: float = 0.5,
    similarity_boost: float = 0.75,
) -> AsyncIterator[bytes]:
    """Stream MP3 chunks of synthesized speech for the given text.

    Yields raw MP3 bytes. Caller wraps this in a StreamingResponse with
    `media_type='audio/mpeg'`. In dry-run mode we yield a silent stub so
    the browser audio element still fires `canplay` / `ended`.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("text is required")
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]

    # Pick voice + model per surface
    if surface == "friday":
        voice_id = voice_id or FRIDAY_VOICE_ID
        model_id = model_id or FRIDAY_MODEL
    else:
        voice_id = voice_id or DEFAULT_VOICE_ID
        model_id = model_id or LONG_MODEL

    if is_dry_run():
        _log_synthesis(
            surface=surface, voice_id=voice_id, model_id=model_id,
            text=text, dry_run=True,
        )
        async for chunk in _dry_run_stream():
            yield chunk
        return

    # Real synth
    try:
        from elevenlabs import VoiceSettings
        client = _get_client()
        settings = VoiceSettings(
            stability=stability,
            similarity_boost=similarity_boost,
        )
        stream = client.text_to_speech.stream(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            voice_settings=settings,
        )
        # SDK returns an async iterator of bytes chunks
        async for chunk in stream:
            if chunk:
                yield chunk
        _log_synthesis(
            surface=surface, voice_id=voice_id, model_id=model_id,
            text=text, dry_run=False,
        )
    except Exception as exc:  # pragma: no cover — network path
        _log_synthesis(
            surface=surface, voice_id=voice_id, model_id=model_id,
            text=text, dry_run=False, error=str(exc),
        )
        # Fall back to silent stub so the frontend audio element doesn't
        # explode — surfaces the error via response header set by the
        # caller.
        log.exception("ElevenLabs stream failed — falling back to silent stub")
        async for chunk in _dry_run_stream():
            yield chunk


__all__ = [
    "ELEVENLABS_API_KEY",
    "DEFAULT_VOICE_ID",
    "FRIDAY_VOICE_ID",
    "LONG_MODEL",
    "FRIDAY_MODEL",
    "MAX_TEXT_CHARS",
    "CURATED_VOICES",
    "TTS_LOG",
    "is_placeholder",
    "is_dry_run",
    "list_voices",
    "synthesize_stream",
]
