"""Mock email connector — loads seed emails from a JSON file."""

from __future__ import annotations

from pathlib import Path

from src.auth import read_json_file
from src.models.email import Email


def load_emails(data_file: Path) -> list[Email]:
    """Read seed emails from a JSON file and return Email model instances."""
    raw = read_json_file(data_file, default=[])
    return [Email.model_validate(entry) for entry in raw]

