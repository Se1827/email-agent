"""Structured JSON logging setup."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from src.observability import current_trace_context


class JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        entry.update(current_trace_context())

        # Merge any extra fields passed via the ``extra`` kwarg.
        for key in (
            "model",
            "prompt_chars",
            "latency_s",
            "reply_chars",
            "email_id",
            "priority",
            "category",
            "pii_redacted",
            "pii_masked",
            "pii_types",
            "storage_enabled",
            "storage_event",
            "otel_enabled",
            "otel_service_name",
            "otel_exporter",
            "eval_case_id",
            "eval_score",
        ):
            value = getattr(record, key, None)
            if value is not None:
                entry[key] = value

        if record.exc_info and record.exc_info[1]:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger with JSON output to stderr."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(handler)

    # Quiet down noisy third-party loggers.
    for name in ("httpx", "httpcore", "openai", "watchfiles"):
        logging.getLogger(name).setLevel(logging.WARNING)
