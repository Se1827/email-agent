"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Resolve paths relative to the project root (one level up from src/).
PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    groq_api_key: str
    groq_model: str
    log_level: str
    api_port: int
    ui_port: int
    data_dir: Path
    pii_mode: str

    # Email source: "mock" (use seed JSON) or "imap" (connect to real mailbox)
    email_source: str
    # Email load mode: source_only, db_then_source, or db_only
    email_load_mode: str

    # IMAP settings (only needed when email_source == "imap")
    imap_host: str
    imap_port: int
    imap_user: str
    imap_pass: str
    imap_mailbox: str
    imap_use_ssl: bool
    imap_fetch_limit: int

    # Optional encrypted PostgreSQL storage.
    database_url: str
    storage_encryption_key: str
    storage_enabled: bool

    # Optional OpenTelemetry tracing.
    otel_enabled: bool
    otel_service_name: str
    otel_exporter_otlp_endpoint: str

    # Draft quality default.
    default_draft_quality: str

    @classmethod
    def from_env(cls) -> Settings:
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key or api_key == "gsk_your-key-here":
            raise RuntimeError(
                "GROQ_API_KEY is not set. "
                "Copy .env.example to .env and fill in your key."
            )
        return cls(
            groq_api_key=api_key,
            groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            api_port=int(os.getenv("API_PORT", "8000")),
            ui_port=int(os.getenv("UI_PORT", "8501")),
            data_dir=PROJECT_ROOT / "data",
            pii_mode=os.getenv("PII_MODE", "strict_presidio"),
            email_source=os.getenv("EMAIL_SOURCE", "mock"),
            email_load_mode=os.getenv("EMAIL_LOAD_MODE", "db_then_source"),
            imap_host=os.getenv("IMAP_HOST", ""),
            imap_port=int(os.getenv("IMAP_PORT", "993")),
            imap_user=os.getenv("IMAP_USER", ""),
            imap_pass=os.getenv("IMAP_PASS", ""),
            imap_mailbox=os.getenv("IMAP_MAILBOX", "INBOX"),
            imap_use_ssl=os.getenv("IMAP_USE_SSL", "true").lower() == "true",
            imap_fetch_limit=int(os.getenv("IMAP_FETCH_LIMIT", "20")),
            database_url=os.getenv("DATABASE_URL", ""),
            storage_encryption_key=os.getenv("STORAGE_ENCRYPTION_KEY", ""),
            storage_enabled=os.getenv("STORAGE_ENABLED", "false").lower() == "true",
            otel_enabled=os.getenv("OTEL_ENABLED", "false").lower() == "true",
            otel_service_name=os.getenv("OTEL_SERVICE_NAME", "email-agent"),
            otel_exporter_otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
            default_draft_quality=os.getenv("DEFAULT_DRAFT_QUALITY", "balanced"),
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the singleton Settings, creating it on first call.

    Lazy so that test imports don't crash when GROQ_API_KEY is unset.
    """
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings
