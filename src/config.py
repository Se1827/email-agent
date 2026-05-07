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
