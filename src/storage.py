"""Encrypted PostgreSQL application storage.

Storage is intentionally broad: emails, calendar context, workflow events,
LLM interactions, approvals, and evaluation artifacts all use the same
encrypted-record table. Small non-sensitive metadata columns keep lookups
efficient while the full payload stays encrypted before it reaches Postgres.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

from src.observability import span

log = logging.getLogger(__name__)

try:
    import psycopg
    from psycopg.types.json import Jsonb
except Exception:  # pragma: no cover - dependency may be absent until configured.
    psycopg = None
    Jsonb = None  # type: ignore[assignment]


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS encrypted_records (
    id UUID PRIMARY KEY,
    record_type TEXT NOT NULL,
    record_id TEXT,
    email_id TEXT,
    thread_id TEXT,
    source TEXT,
    occurred_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ciphertext BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (record_type, record_id)
);

CREATE INDEX IF NOT EXISTS idx_encrypted_records_type_time
    ON encrypted_records (record_type, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_encrypted_records_email
    ON encrypted_records (email_id);
CREATE INDEX IF NOT EXISTS idx_encrypted_records_thread
    ON encrypted_records (thread_id);
CREATE INDEX IF NOT EXISTS idx_encrypted_records_metadata
    ON encrypted_records USING GIN (metadata);
"""


@dataclass(frozen=True)
class StoredRecord:
    id: str
    record_type: str
    record_id: str
    occurred_at: str


@dataclass(frozen=True)
class _StorageTask:
    func: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


class StorageWriter:
    """Small background writer so persistence never blocks request handling."""

    def __init__(self, *, max_queue_size: int = 1000) -> None:
        self._queue: queue.Queue[_StorageTask | None] = queue.Queue(maxsize=max_queue_size)
        self._thread = threading.Thread(
            target=self._run,
            name="encrypted-storage-writer",
            daemon=True,
        )
        self._thread.start()

    def enqueue(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> bool:
        try:
            self._queue.put_nowait(_StorageTask(func=func, args=args, kwargs=kwargs))
            return True
        except queue.Full:
            log.warning(
                "storage_queue_full",
                extra={"storage_enabled": True, "storage_event": getattr(func, "__name__", "unknown")},
            )
            return False

    def flush(self, *, timeout_s: float = 5.0) -> None:
        self._queue.join()

    def _run(self) -> None:
        while True:
            task = self._queue.get()
            try:
                if task is None:
                    return
                task.func(*task.args, **task.kwargs)
            except Exception:
                log.exception(
                    "storage_write_failed",
                    extra={
                        "storage_enabled": True,
                        "storage_event": getattr(task.func, "__name__", "unknown") if task else "unknown",
                    },
                )
            finally:
                self._queue.task_done()


_writer: StorageWriter | None = None


def generate_encryption_key() -> str:
    """Return a Fernet key suitable for STORAGE_ENCRYPTION_KEY."""
    return Fernet.generate_key().decode("ascii")


def storage_configured() -> bool:
    return bool(
        os.getenv("STORAGE_ENABLED", "false").lower() == "true"
        and os.getenv("DATABASE_URL")
        and os.getenv("STORAGE_ENCRYPTION_KEY")
    )


def get_storage_writer() -> StorageWriter | None:
    """Return the shared async writer, or None when storage is disabled."""
    global _writer
    if not storage_configured():
        return None
    if _writer is None:
        _writer = StorageWriter()
    return _writer


def init_storage() -> None:
    """Create the encrypted storage schema when PostgreSQL is configured."""
    if not storage_configured():
        log.info("storage_disabled", extra={"storage_enabled": False})
        return
    _require_psycopg()

    with span("storage.init", storage_enabled=True):
        with psycopg.connect(_database_url()) as conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_SQL)
            conn.commit()
    log.info("storage_ready", extra={"storage_enabled": True})


def store_email(email: Any, *, source: str) -> StoredRecord | None:
    """Persist a full email payload encrypted, with efficient metadata."""
    payload = email.model_dump(mode="json") if hasattr(email, "model_dump") else dict(email)
    metadata = {
        "sender_hash": _stable_hash(payload.get("sender", "")),
        "subject_hash": _stable_hash(payload.get("subject", "")),
        "recipient_count": len(payload.get("recipients", []) or []),
        "has_classification": bool(payload.get("classification")),
        "has_draft": bool(payload.get("draft_reply")),
    }
    return upsert_record(
        "email",
        record_id=payload["id"],
        payload=payload,
        email_id=payload["id"],
        thread_id=payload.get("thread_id"),
        source=source,
        occurred_at=payload.get("timestamp"),
        metadata=metadata,
    )


def store_calendar_event(event: Any, *, source: str = "calendar") -> StoredRecord | None:
    payload = event.model_dump(mode="json") if hasattr(event, "model_dump") else dict(event)
    record_id = _stable_hash(json.dumps(payload, sort_keys=True))
    metadata = {
        "title_hash": _stable_hash(payload.get("title", "")),
        "attendee_count": len(payload.get("attendees", []) or []),
    }
    return upsert_record(
        "calendar_event",
        record_id=record_id,
        payload=payload,
        source=source,
        occurred_at=payload.get("start"),
        metadata=metadata,
    )


def record_event(
    event_type: str,
    payload: dict[str, Any],
    *,
    subject_id: str | None = None,
    email_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> StoredRecord | None:
    """Persist a workflow event such as classification, draft, approval."""
    record_id = str(uuid4())
    return upsert_record(
        "event",
        record_id=record_id,
        payload={
            "event_type": event_type,
            "subject_id": subject_id,
            "payload": payload,
        },
        email_id=email_id or subject_id,
        source=event_type,
        metadata={"event_type": event_type, **(metadata or {})},
    )


def record_llm_interaction(
    *,
    purpose: str,
    model: str,
    messages: list[dict[str, str]],
    response: str,
    latency_s: float,
    metadata: dict[str, Any] | None = None,
) -> StoredRecord | None:
    """Store the exact prompt sent to the model and its response."""
    prompt_chars = sum(len(m.get("content", "")) for m in messages)
    return upsert_record(
        "llm_interaction",
        record_id=str(uuid4()),
        payload={
            "purpose": purpose,
            "model": model,
            "messages": messages,
            "response": response,
            "latency_s": latency_s,
        },
        source=purpose,
        metadata={
            "purpose": purpose,
            "model": model,
            "prompt_chars": prompt_chars,
            "response_chars": len(response),
            **(metadata or {}),
        },
    )


def record_eval_case(run_id: str, case_id: str, payload: dict[str, Any]) -> StoredRecord | None:
    return upsert_record(
        "eval_case",
        record_id=f"{run_id}:{case_id}",
        payload=payload,
        source="evaluation",
        metadata={
            "run_id": run_id,
            "case_id": case_id,
            "passed": bool(payload.get("passed")),
            "score": payload.get("score", 0),
        },
    )


def record_eval_run(run_id: str, payload: dict[str, Any]) -> StoredRecord | None:
    return upsert_record(
        "eval_run",
        record_id=run_id,
        payload=payload,
        source="evaluation",
        metadata={
            "run_id": run_id,
            "score": payload.get("score", 0),
            "case_count": payload.get("case_count", 0),
        },
    )


def upsert_record(
    record_type: str,
    *,
    record_id: str,
    payload: dict[str, Any],
    email_id: str | None = None,
    thread_id: str | None = None,
    source: str | None = None,
    occurred_at: str | datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> StoredRecord | None:
    """Encrypt and upsert a typed application record."""
    if not storage_configured():
        return None
    _require_psycopg()

    row_id = str(uuid4())
    occurred = _coerce_datetime(occurred_at)
    ciphertext = encrypt_payload(payload, _encryption_key())
    metadata = metadata or {}

    with span("storage.upsert_record", storage_event=record_type):
        with psycopg.connect(_database_url()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO encrypted_records (
                        id, record_type, record_id, email_id, thread_id, source,
                        occurred_at, metadata, ciphertext
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (record_type, record_id)
                    DO UPDATE SET
                        email_id = EXCLUDED.email_id,
                        thread_id = EXCLUDED.thread_id,
                        source = EXCLUDED.source,
                        occurred_at = EXCLUDED.occurred_at,
                        metadata = EXCLUDED.metadata,
                        ciphertext = EXCLUDED.ciphertext,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    (
                        row_id,
                        record_type,
                        record_id,
                        email_id,
                        thread_id,
                        source,
                        occurred,
                        Jsonb(metadata),
                        ciphertext,
                    ),
                )
                stored_id = str(cur.fetchone()[0])
            conn.commit()

    log.info(
        "storage_record_upserted",
        extra={"storage_enabled": True, "storage_event": record_type},
    )
    return StoredRecord(
        id=stored_id,
        record_type=record_type,
        record_id=record_id,
        occurred_at=occurred.isoformat(),
    )


def safe_store_email(email: Any, *, source: str) -> None:
    _enqueue(store_email, email, source=source)


def safe_store_calendar_event(event: Any, *, source: str = "calendar") -> None:
    _enqueue(store_calendar_event, event, source=source)


def safe_record_event(
    event_type: str,
    payload: dict[str, Any],
    *,
    subject_id: str | None = None,
    email_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    _enqueue(
        record_event,
        event_type,
        payload,
        subject_id=subject_id,
        email_id=email_id,
        metadata=metadata,
    )


def safe_record_llm_interaction(**kwargs: Any) -> None:
    _enqueue(record_llm_interaction, **kwargs)


def safe_record_eval_case(run_id: str, case_id: str, payload: dict[str, Any]) -> None:
    _enqueue(record_eval_case, run_id, case_id, payload)


def safe_record_eval_run(run_id: str, payload: dict[str, Any]) -> None:
    _enqueue(record_eval_run, run_id, payload)


def encrypt_payload(payload: dict[str, Any], key: str) -> bytes:
    fernet = Fernet(_normalized_key(key))
    return fernet.encrypt(json.dumps(payload, default=str).encode("utf-8"))


def decrypt_payload(ciphertext: bytes, key: str) -> dict[str, Any]:
    fernet = Fernet(_normalized_key(key))
    try:
        raw = fernet.decrypt(ciphertext)
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt payload with the configured key") from exc
    return json.loads(raw.decode("utf-8"))


def _enqueue(func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    writer = get_storage_writer()
    if writer is None:
        return
    writer.enqueue(func, *args, **kwargs)


def _require_psycopg() -> None:
    if psycopg is None or Jsonb is None:
        raise RuntimeError("psycopg[binary] is required when STORAGE_ENABLED=true")


def _coerce_datetime(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def _normalized_key(key: str) -> bytes:
    return key.encode("ascii")


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _database_url() -> str:
    return os.environ["DATABASE_URL"]


def _encryption_key() -> str:
    return os.environ["STORAGE_ENCRYPTION_KEY"]
