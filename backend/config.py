import logging
import os
import sys

from pydantic_settings import BaseSettings

_logger = logging.getLogger("createstage.config")


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./quotes.db"
    SECRET_KEY: str = "dev-secret-key"
    COMPANY_NAME: str = "CreateStage Fabrication"
    COMPANY_EMAIL: str = "info@createstage.com"
    COMPANY_PHONE: str = ""
    LABOR_RATE_DEFAULT: float = 125.00
    MARKUP_DEFAULT: float = 1.35
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_FAST_MODEL: str = "claude-opus-4-6"
    CLAUDE_DEEP_MODEL: str = "claude-opus-4-6"
    CLAUDE_REVIEW_MODEL: str = "claude-opus-4-6"

    # Auth — v2
    JWT_SECRET: str = ""  # REQUIRED in production — fail loudly if missing at auth time
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_EXPIRE_DAYS: int = 30

    # Email (Resend)
    RESEND_API_KEY: str = ""
    RESEND_FROM: str = "CreateQuote <onboarding@resend.dev>"
    APP_URL: str = "http://localhost:8000"
    APP_ADMIN_EMAIL: str = ""  # Bypasses email verification gate

    # Cloudflare R2 — optional now, required in Session 3
    CLOUDFLARE_R2_ACCOUNT_ID: str = ""
    CLOUDFLARE_R2_ACCESS_KEY_ID: str = ""
    CLOUDFLARE_R2_SECRET_ACCESS_KEY: str = ""
    CLOUDFLARE_R2_BUCKET: str = "createstage-quotes"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()


def validate_production_config():
    """Validate config when PRODUCTION=1. Fail fast if secrets are weak."""
    is_prod = os.environ.get("PRODUCTION") == "1"

    # Always log env var checklist
    env_checklist = {
        "DATABASE_URL": bool(os.environ.get("DATABASE_URL")),
        "JWT_SECRET": bool(os.environ.get("JWT_SECRET")),
        "ADMIN_SECRET": bool(os.environ.get("ADMIN_SECRET")),
        "RESEND_API_KEY": bool(os.environ.get("RESEND_API_KEY")),
        "STRIPE_SECRET_KEY": bool(os.environ.get("STRIPE_SECRET_KEY")),
        "ALLOWED_ORIGINS": bool(os.environ.get("ALLOWED_ORIGINS")),
    }
    for var, present in env_checklist.items():
        status = "SET" if present else "MISSING"
        _logger.info("[CONFIG] %s: %s", var, status)

    if not is_prod:
        return

    # Production-only checks — fail hard
    if settings.SECRET_KEY == "dev-secret-key":
        _logger.critical("FATAL: SECRET_KEY is the dev default in production. Set a real secret.")
        sys.exit(1)

    if not settings.JWT_SECRET:
        _logger.critical("FATAL: JWT_SECRET is empty in production. Set it to a random 256-bit hex string.")
        sys.exit(1)
