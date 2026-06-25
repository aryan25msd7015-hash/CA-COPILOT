"""
Application settings loaded from environment variables with .env fallback.
In production, secrets are read from AWS Secrets Manager (see services/secrets_service.py).
"""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── Database ───────────────────────────────────────────────────────────
    DATABASE_URL: str

    # ── Redis / Celery ─────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── AWS ────────────────────────────────────────────────────────────────
    AWS_REGION: str = "ap-south-1"
    S3_BUCKET: str

    # ── JWT ────────────────────────────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Azure Document Intelligence ────────────────────────────────────────
    AZURE_DOC_ENDPOINT: str = ""
    AZURE_DOC_KEY: str = ""

    # ── LLM providers ─────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # ── WhatsApp (Meta Business API) ───────────────────────────────────────
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "verify"

    # ── General ────────────────────────────────────────────────────────────
    FRONTEND_URL: str = "http://localhost:3000"
    ENV: str = "development"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton instance used across the application
settings = Settings()
