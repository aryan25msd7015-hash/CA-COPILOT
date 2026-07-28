"""Unit tests for free-tier LLM gateway selection."""
from app.engines import llm_gateway


def test_default_models_include_free_tier():
    assert llm_gateway.DEFAULT_MODELS["groq"] == "llama-3.1-8b-instant"
    assert llm_gateway.DEFAULT_MODELS["gemini"] == "gemini-2.0-flash"
    assert "free" in llm_gateway.DEFAULT_MODELS["openrouter"]


def test_capability_falls_back_without_keys(monkeypatch):
    monkeypatch.setattr(llm_gateway.settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(llm_gateway.settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(llm_gateway.settings, "GROQ_API_KEY", "")
    monkeypatch.setattr(llm_gateway.settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(llm_gateway.settings, "OPENROUTER_API_KEY", "")
    status = llm_gateway.capability_status()
    assert status["llm_provider"] == "deterministic_fallback"
    assert status["fallback_reason"]


def test_groq_selected_as_free_tier(monkeypatch):
    monkeypatch.setattr(llm_gateway.settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(llm_gateway.settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(llm_gateway.settings, "GROQ_API_KEY", "gsk_test")
    monkeypatch.setattr(llm_gateway.settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(llm_gateway.settings, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(llm_gateway.settings, "LLM_PROVIDER_ORDER", "anthropic,openai,groq,gemini,openrouter")
    monkeypatch.setattr(llm_gateway.settings, "LLM_SQL_MODEL", "")
    active = llm_gateway.active_provider()
    assert active is not None
    assert active["provider"] == "groq"
    assert active["tier"] == "free"
    assert active["model"] == "llama-3.1-8b-instant"


def test_paid_anthropic_outranks_free_tier(monkeypatch):
    monkeypatch.setattr(llm_gateway.settings, "ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.setattr(llm_gateway.settings, "GROQ_API_KEY", "gsk_test")
    monkeypatch.setattr(llm_gateway.settings, "LLM_PROVIDER_ORDER", "anthropic,openai,groq,gemini,openrouter")
    active = llm_gateway.active_provider()
    assert active is not None
    assert active["provider"] == "anthropic"
    assert active["tier"] == "paid"
