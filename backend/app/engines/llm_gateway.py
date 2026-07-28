"""Multi-provider LLM gateway with free-tier defaults for NL query / SQL translation.

Provider priority (first configured key wins, overridable via LLM_PROVIDER_ORDER):
  1. anthropic  (paid)  — claude-sonnet-4-20250514
  2. openai     (paid)  — gpt-4o-mini
  3. groq       (free)  — llama-3.1-8b-instant
  4. gemini     (free)  — gemini-2.0-flash
  5. openrouter (free)  — meta-llama/llama-3.2-3b-instruct:free

Uses httpx for Groq / Gemini / OpenRouter so no extra SDKs are required.
Anthropic / OpenAI SDKs are imported optionally when their keys are present.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import settings

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o-mini",
    "groq": "llama-3.1-8b-instant",
    "gemini": "gemini-2.0-flash",
    "openrouter": "meta-llama/llama-3.2-3b-instruct:free",
}

FREE_TIER_PROVIDERS = ("groq", "gemini", "openrouter")


@dataclass
class LlmCompletion:
    text: str
    provider: str
    model: str


def _configured(value: str | None) -> bool:
    return bool(value and str(value).strip())


def provider_order() -> list[str]:
    raw = (settings.LLM_PROVIDER_ORDER or "anthropic,openai,groq,gemini,openrouter").strip()
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


def model_for(provider: str) -> str:
    override = (settings.LLM_SQL_MODEL or "").strip()
    if override:
        return override
    return DEFAULT_MODELS.get(provider, DEFAULT_MODELS["groq"])


def available_providers() -> list[dict[str, Any]]:
    checks = {
        "anthropic": _configured(settings.ANTHROPIC_API_KEY),
        "openai": _configured(settings.OPENAI_API_KEY),
        "groq": _configured(settings.GROQ_API_KEY),
        "gemini": _configured(settings.GEMINI_API_KEY),
        "openrouter": _configured(settings.OPENROUTER_API_KEY),
    }
    return [
        {
            "provider": name,
            "configured": checks[name],
            "model": model_for(name),
            "tier": "free" if name in FREE_TIER_PROVIDERS else "paid",
        }
        for name in provider_order()
        if name in checks
    ]


def active_provider() -> dict[str, Any] | None:
    for item in available_providers():
        if item["configured"]:
            return item
    return None


def capability_status() -> dict[str, Any]:
    active = active_provider()
    providers = available_providers()
    if not active:
        return {
            "llm_provider": "deterministic_fallback",
            "llm_model": None,
            "llm_tier": None,
            "embedding_provider": "openai" if _configured(settings.OPENAI_API_KEY) else "keyword_and_sql",
            "rag_mode": "semantic_vector" if _configured(settings.OPENAI_API_KEY) else "keyword_grounded",
            "fallback_reason": "No LLM API key configured (set GROQ_API_KEY / GEMINI_API_KEY for free tier)",
            "providers": providers,
        }
    return {
        "llm_provider": active["provider"],
        "llm_model": active["model"],
        "llm_tier": active["tier"],
        "embedding_provider": "openai" if _configured(settings.OPENAI_API_KEY) else "keyword_and_sql",
        "rag_mode": "semantic_vector" if _configured(settings.OPENAI_API_KEY) else "keyword_grounded",
        "fallback_reason": None,
        "providers": providers,
    }


def _complete_anthropic(system: str, user: str, max_tokens: int) -> LlmCompletion:
    from anthropic import Anthropic

    model = model_for("anthropic")
    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = response.content[0].text.strip()
    return LlmCompletion(text=text, provider="anthropic", model=model)


def _complete_openai_compatible(
    *,
    provider: str,
    base_url: str,
    api_key: str,
    system: str,
    user: str,
    max_tokens: int,
    extra_headers: dict[str, str] | None = None,
) -> LlmCompletion:
    import httpx

    model = model_for(provider)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **(extra_headers or {}),
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    with httpx.Client(timeout=45.0) as client:
        response = client.post(f"{base_url.rstrip('/')}/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    text = (data["choices"][0]["message"]["content"] or "").strip()
    return LlmCompletion(text=text, provider=provider, model=model)


def _complete_gemini(system: str, user: str, max_tokens: int) -> LlmCompletion:
    import httpx

    model = model_for("gemini")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={settings.GEMINI_API_KEY}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens},
    }
    with httpx.Client(timeout=45.0) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
    parts = data["candidates"][0]["content"]["parts"]
    text = "".join(part.get("text", "") for part in parts).strip()
    return LlmCompletion(text=text, provider="gemini", model=model)


def complete_text(system: str, user: str, *, max_tokens: int = 800) -> LlmCompletion:
    """Try providers in order; raise RuntimeError if none succeed."""
    errors: list[str] = []
    for item in available_providers():
        if not item["configured"]:
            continue
        provider = item["provider"]
        try:
            if provider == "anthropic":
                return _complete_anthropic(system, user, max_tokens)
            if provider == "openai":
                return _complete_openai_compatible(
                    provider="openai",
                    base_url="https://api.openai.com/v1",
                    api_key=settings.OPENAI_API_KEY,
                    system=system,
                    user=user,
                    max_tokens=max_tokens,
                )
            if provider == "groq":
                return _complete_openai_compatible(
                    provider="groq",
                    base_url="https://api.groq.com/openai/v1",
                    api_key=settings.GROQ_API_KEY,
                    system=system,
                    user=user,
                    max_tokens=max_tokens,
                )
            if provider == "gemini":
                return _complete_gemini(system, user, max_tokens)
            if provider == "openrouter":
                return _complete_openai_compatible(
                    provider="openrouter",
                    base_url="https://openrouter.ai/api/v1",
                    api_key=settings.OPENROUTER_API_KEY,
                    system=system,
                    user=user,
                    max_tokens=max_tokens,
                    extra_headers={
                        "HTTP-Referer": settings.FRONTEND_URL or "https://localhost",
                        "X-Title": "CA Copilot",
                    },
                )
        except Exception as exc:  # noqa: BLE001 — try next provider
            errors.append(f"{provider}: {exc}")
            continue
    detail = "; ".join(errors) if errors else "no providers configured"
    raise RuntimeError(f"LLM completion unavailable ({detail})")
