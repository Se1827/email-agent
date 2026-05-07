"""Regex-based PII detection and redaction.

Catches common PII patterns — credit card numbers, SSNs, US phone numbers,
and bank account/routing numbers.  Intentionally lightweight; swap in a
heavier library (e.g. Presidio) if you need broader coverage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# Each pattern maps a human-readable label to a compiled regex.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "credit_card",
        re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    ),
    (
        "ssn",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    ),
    (
        "phone",
        re.compile(
            r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"
        ),
    ),
    (
        "bank_account",
        re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
    ),
    (
        "routing_number",
        re.compile(r"\brouting[:\s]*\d{9}\b", re.IGNORECASE),
    ),
]


@dataclass
class RedactionResult:
    text: str
    found_types: list[str] = field(default_factory=list)

    @property
    def was_redacted(self) -> bool:
        return len(self.found_types) > 0


def redact(text: str) -> RedactionResult:
    """Scan *text* for PII patterns and replace matches with placeholders."""
    found: list[str] = []
    for label, pattern in _PATTERNS:
        if pattern.search(text):
            text = pattern.sub(f"[REDACTED-{label.upper()}]", text)
            if label not in found:
                found.append(label)
    return RedactionResult(text=text, found_types=found)
