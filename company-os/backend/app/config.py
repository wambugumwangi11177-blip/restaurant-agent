"""
app/config.py
─────────────
All configuration comes from environment variables, read once into a frozen
Settings object. `check_startup()` is the config guard: in production it refuses
to boot with default or missing secrets instead of running insecurely; in every
environment it reports which optional integrations (LLM, Twilio, SMTP) are
unconfigured so the features that need them degrade visibly, never silently.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

DEV_JWT_SECRET = "dev-only-insecure-jwt-secret-change-me"


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    env: str = "development"  # development | test | production
    database_url: str = "postgresql+psycopg2://cos:cos@localhost:5432/cos_dev"
    jwt_secret: str = DEV_JWT_SECRET
    jwt_ttl_minutes: int = 60 * 12
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:3000"])
    public_base_url: str = "http://localhost:8000"
    app_timezone: str = "Africa/Nairobi"
    default_currency: str = "KES"

    # LLM providers — checked in this order, first key present wins.
    openrouter_api_key: str = ""
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    llm_timeout_seconds: float = 120.0  # adaptive-thinking models can take a while
    daily_llm_spend_cap_usd: float = 5.0

    # Channels
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""  # e.g. whatsapp:+14155238886
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # Login lockout
    max_failed_logins: int = 5
    lockout_minutes: int = 15

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def llm_provider(self) -> str | None:
        if self.openrouter_api_key:
            return "openrouter"
        if self.anthropic_api_key:
            return "anthropic"
        if self.groq_api_key:
            return "groq"
        return None

    @property
    def twilio_configured(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token and self.twilio_whatsapp_from)

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)


def _load() -> Settings:
    e = os.environ.get
    return Settings(
        env=e("ENV", "development"),
        database_url=e("DATABASE_URL", Settings.database_url),
        jwt_secret=e("JWT_SECRET", DEV_JWT_SECRET),
        jwt_ttl_minutes=int(e("JWT_TTL_MINUTES", "720")),
        cors_origins=_csv(e("CORS_ORIGINS", "http://localhost:3000")),
        public_base_url=e("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/"),
        app_timezone=e("APP_TIMEZONE", "Africa/Nairobi"),
        default_currency=e("DEFAULT_CURRENCY", "KES"),
        openrouter_api_key=e("OPENROUTER_API_KEY", ""),
        anthropic_api_key=e("ANTHROPIC_API_KEY", ""),
        groq_api_key=e("GROQ_API_KEY", ""),
        llm_timeout_seconds=float(e("LLM_TIMEOUT_SECONDS", "120")),
        daily_llm_spend_cap_usd=float(e("DAILY_LLM_SPEND_CAP_USD", "5.0")),
        twilio_account_sid=e("TWILIO_ACCOUNT_SID", ""),
        twilio_auth_token=e("TWILIO_AUTH_TOKEN", ""),
        twilio_whatsapp_from=e("TWILIO_WHATSAPP_FROM", ""),
        smtp_host=e("SMTP_HOST", ""),
        smtp_port=int(e("SMTP_PORT", "587")),
        smtp_user=e("SMTP_USER", ""),
        smtp_password=e("SMTP_PASSWORD", ""),
        smtp_from=e("SMTP_FROM", ""),
        max_failed_logins=int(e("MAX_FAILED_LOGINS", "5")),
        lockout_minutes=int(e("LOCKOUT_MINUTES", "15")),
    )


@lru_cache
def get_settings() -> Settings:
    return _load()


class ConfigError(RuntimeError):
    pass


def check_startup(s: Settings) -> list[str]:
    """Raise ConfigError on fatal misconfiguration; return warnings otherwise."""
    fatal: list[str] = []
    warnings: list[str] = []

    if s.env not in {"development", "test", "production"}:
        fatal.append(f"ENV must be development|test|production, got {s.env!r}")

    if s.is_production:
        if s.jwt_secret == DEV_JWT_SECRET or len(s.jwt_secret) < 32:
            fatal.append("JWT_SECRET must be set to a random value of at least 32 characters")
        if "localhost" in s.database_url or "127.0.0.1" in s.database_url:
            fatal.append("DATABASE_URL points at localhost in production")
        if not s.public_base_url.startswith("https://"):
            fatal.append("PUBLIC_BASE_URL must be https:// in production (Twilio signature validation uses it)")
        if any(o == "*" for o in s.cors_origins):
            fatal.append("CORS_ORIGINS must not be '*' in production")

    if s.llm_provider is None:
        warnings.append("No LLM key set: LLM agents will report 'llm_unavailable'; deterministic agents still run")
    if not s.twilio_configured:
        warnings.append("Twilio not configured: WhatsApp sends will fail with 'channel_not_configured'")
    if not s.smtp_configured:
        warnings.append("SMTP not configured: email sends will fail with 'channel_not_configured'")

    if fatal:
        raise ConfigError("; ".join(fatal))
    return warnings
