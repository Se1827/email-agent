"""Mock email connector — loads seed emails from a JSON file."""

from __future__ import annotations

import json
from pathlib import Path

from src.models.email import Email


def load_emails(data_file: Path) -> list[Email]:
    """Read seed emails from a JSON file and return Email model instances."""
    with open(data_file) as f:
        raw = json.load(f)
    return [Email.model_validate(entry) for entry in raw]
