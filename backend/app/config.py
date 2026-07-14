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
    RATE_LIMIT_BACKEND: str = "auto"  # auto | memory | redis
    RATE_LIMIT_REDIS_PREFIX: str = "ca-copilot:rate-limit"

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

    # Email delivery
    EMAIL_PROVIDER: str = "development"  # development | smtp
    EMAIL_FROM: str = "CA Copilot <no-reply@localhost>"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False

    # Payments
    PAYMENT_PROVIDER: str = "none"  # none | razorpay
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    PAYMENT_LINK_EXPIRE_DAYS: int = 30

    # Emergent-managed Google Auth
    GOOGLE_SIGNUP_MODE: str = "auto_pending"       # invited_only | auto_pending | auto_partner
    GOOGLE_ALLOWED_DOMAINS: str = ""               # comma-separated; empty = anyone

    # Observability
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    METRICS_ENABLED: bool = True
    METRICS_BEARER_TOKEN: str = ""

    # ── General ────────────────────────────────────────────────────────────
    FRONTEND_URL: str = "http://localhost:3000"
    ENV: str = "development"
    SQL_ECHO: bool = False
    TRUSTED_HOSTS: str = "localhost,127.0.0.1,testserver"
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS: int = 24
    MAX_FAILED_LOGIN_ATTEMPTS: int = 5
    ACCOUNT_LOCKOUT_MINUTES: int = 15

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton instance used across the application
settings = Settings()
