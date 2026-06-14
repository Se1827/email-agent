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
    message_id TEXT,
    in_reply_to TEXT,
    is_sent BOOLEAN NOT NULL DEFAULT FALSE,
    occurred_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ciphertext BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (record_type, record_id)
);

ALTER TABLE encrypted_records ADD COLUMN IF NOT EXISTS message_id TEXT;
ALTER TABLE encrypted_records ADD COLUMN IF NOT EXISTS in_reply_to TEXT;
ALTER TABLE encrypted_records ADD COLUMN IF NOT EXISTS is_sent BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_encrypted_records_type_time
    ON encrypted_records (record_type, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_encrypted_records_email
    ON encrypted_records (email_id);
CREATE INDEX IF NOT EXISTS idx_encrypted_records_thread
    ON encrypted_records (thread_id);
CREATE INDEX IF NOT EXISTS idx_encrypted_records_message_id
    ON encrypted_records (message_id);
CREATE INDEX IF NOT EXISTS idx_encrypted_records_metadata
    ON encrypted_records USING GIN (metadata);
"""

PGVECTOR_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS semantic_memories (
    id UUID PRIMARY KEY,
    memory_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    email_id TEXT,
    thread_id TEXT,
    summary TEXT NOT NULL,
    embedding VECTOR(384),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (memory_type, subject_id)
);

CREATE INDEX IF NOT EXISTS idx_semantic_memories_type
    ON semantic_memories (memory_type);
CREATE INDEX IF NOT EXISTS idx_semantic_memories_email
    ON semantic_memories (email_id);
CREATE INDEX IF NOT EXISTS idx_semantic_memories_thread
    ON semantic_memories (thread_id);
CREATE INDEX IF NOT EXISTS idx_semantic_memories_metadata
    ON semantic_memories USING GIN (metadata);

-- Sender profiles for personalization and VIP detection
CREATE TABLE IF NOT EXISTS sender_profiles (
    email_address TEXT PRIMARY KEY,
    display_name TEXT,
    relationship TEXT DEFAULT 'unknown',
    tone_preference TEXT DEFAULT 'professional',
    avg_priority TEXT DEFAULT 'normal',
    interaction_count INTEGER DEFAULT 0,
    last_interaction TIMESTAMPTZ,
    is_vip BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- User preferences and standing instructions
CREATE TABLE IF NOT EXISTS user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pref_type TEXT NOT NULL,
    pref_key TEXT NOT NULL,
    pref_value TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (pref_type, pref_key)
);

-- Action items extracted from emails
CREATE TABLE IF NOT EXISTS action_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_id TEXT NOT NULL,
    thread_id TEXT,
    description TEXT NOT NULL,
    due_date TIMESTAMPTZ,
    status TEXT DEFAULT 'pending',
    extracted_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_action_items_email
    ON action_items (email_id);
CREATE INDEX IF NOT EXISTS idx_action_items_status
    ON action_items (status);
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
        _init_pgvector()
    log.info("storage_ready", extra={"storage_enabled": True})

def store_sync_state(state: Any) -> StoredRecord | None:
    """Persist the IMAP incremental sync state for a mailbox."""
    payload = state.model_dump(mode="json") if hasattr(state, "model_dump") else dict(state)
    record_id = f"{payload['account_id']}:{payload['mailbox']}"
    return upsert_record(
        "sync_state",
        record_id=record_id,
        payload=payload,
        source="imap_sync",
        metadata={
            "account_id": payload["account_id"],
            "mailbox": payload["mailbox"],
            "uidvalidity": payload["uidvalidity"],
        },
    )


def load_sync_state(account_id: str, mailbox: str) -> dict[str, Any] | None:
    """Fetch the IMAP incremental sync state for a mailbox."""
    record_id = f"{account_id}:{mailbox}"
    return load_record_payload("sync_state", record_id)


def clear_sync_state(account_id: str, mailbox: str) -> None:
    """Delete the sync state for a mailbox (e.g. on UIDVALIDITY change)."""
    if not storage_configured():
        return
    _require_psycopg()
    record_id = f"{account_id}:{mailbox}"
    with psycopg.connect(_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM encrypted_records WHERE record_type = 'sync_state' AND record_id = %s",
                (record_id,)
            )
        conn.commit()


def store_email(email: Any, *, source: str) -> StoredRecord | None:
    """Persist a full email payload encrypted, with efficient metadata."""
    payload = email.model_dump(mode="json") if hasattr(email, "model_dump") else dict(email)
    inbox = payload.get("inbox") or source
    metadata = {
        "inbox_hash": _stable_hash(inbox),
        "sender_hash": _stable_hash(payload.get("sender", "")),
        "subject_hash": _stable_hash(payload.get("subject", "")),
        "content_hash": email_content_hash(payload),
        "recipient_count": len(payload.get("recipients", []) or []),
        "has_classification": bool(payload.get("classification")),
        "has_draft": bool(payload.get("draft_reply")),
        "is_sent": bool(payload.get("is_sent")),
        "message_id": payload.get("message_id"),
        "in_reply_to": payload.get("in_reply_to"),
    }
    return upsert_record(
        "email",
        record_id=email_record_id(payload["id"], inbox),
        payload=payload,
        email_id=payload["id"],
        thread_id=payload.get("thread_id"),
        source=source,
        occurred_at=payload.get("timestamp"),
        metadata=metadata,
    )


def load_email_state(email_id: str, *, inbox: str | None = None) -> dict[str, Any] | None:
    """Return the latest encrypted email payload for cache hydration."""
    if inbox:
        return load_record_payload("email", email_record_id(email_id, inbox))
    return load_record_payload("email", email_id)


def load_email_states(
    *,
    inbox: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return decrypted saved email payloads, newest first."""
    if not storage_configured():
        return []
    _require_psycopg()

    sql = """
        SELECT ciphertext
        FROM encrypted_records
        WHERE record_type = 'email'
    """
    params: list[Any] = []
    if inbox:
        sql += " AND metadata->>'inbox_hash' = %s"
        params.append(_stable_hash(inbox))
    sql += " ORDER BY occurred_at DESC"
    if limit is not None:
        sql += " LIMIT %s"
        params.append(max(1, limit))

    with psycopg.connect(_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
    return [decrypt_payload(row[0], _encryption_key()) for row in rows]


def email_content_hash(email: Any) -> str:
    """Stable hash of fields that affect classification/drafting."""
    payload = email.model_dump(mode="json") if hasattr(email, "model_dump") else dict(email)
    content = {
        "sender": payload.get("sender", ""),
        "recipients": sorted(payload.get("recipients", []) or []),
        "subject": payload.get("subject", ""),
        "body": payload.get("body", ""),
        "timestamp": str(payload.get("timestamp", "")),
        "thread_id": payload.get("thread_id"),
    }
    return _stable_hash(json.dumps(content, sort_keys=True, default=str))


def email_record_id(email_id: str, inbox: str) -> str:
    """Storage record id scoped to one inbox without leaking the inbox value."""
    return _stable_hash(f"{inbox}:{email_id}")


def store_pii_mappings(
    email_id: str,
    purpose: str,
    mappings: list[Any],
) -> StoredRecord | None:
    """Persist local token->PII mappings encrypted for later rehydration."""
    if not mappings:
        return None
    payload = {
        "email_id": email_id,
        "purpose": purpose,
        "mappings": [
            {
                "token": mapping.token,
                "original": mapping.original,
                "entity_type": mapping.entity_type,
            }
            for mapping in mappings
        ],
    }
    return upsert_record(
        "pii_mapping",
        record_id=f"{email_id}:{purpose}",
        payload=payload,
        email_id=email_id,
        source=purpose,
        metadata={
            "purpose": purpose,
            "mapping_count": len(mappings),
            "entity_types": sorted({mapping.entity_type.lower() for mapping in mappings}),
        },
    )


def store_thread_state(thread_id: str, payload: dict[str, Any]) -> StoredRecord | None:
    """Persist compact conversation state used as agent memory."""
    return upsert_record(
        "thread_state",
        record_id=thread_id,
        payload=payload,
        thread_id=thread_id,
        email_id=payload.get("last_email_id"),
        source="thread_state",
        metadata={
            "priority": payload.get("priority"),
            "category": payload.get("category"),
            "participant_count": len(payload.get("participants", []) or []),
        },
    )


def store_user_preferences(user: str, payload: dict[str, Any]) -> StoredRecord | None:
    """Persist encrypted user drafting preferences."""
    return upsert_record(
        "user_preferences",
        record_id=user,
        payload={"user": user, **payload},
        source="user_preferences",
        metadata={"user_hash": _stable_hash(user)},
    )


def store_semantic_memory(
    *,
    memory_type: str,
    subject_id: str,
    summary: str,
    email_id: str | None = None,
    thread_id: str | None = None,
    embedding: list[float] | None = None,
    metadata: dict[str, Any] | None = None,
) -> StoredRecord | None:
    """Store summary/chunk metadata. Uses pgvector when the extension exists."""
    encrypted = upsert_record(
        "semantic_memory",
        record_id=f"{memory_type}:{subject_id}",
        payload={
            "memory_type": memory_type,
            "subject_id": subject_id,
            "summary": summary,
            "embedding": embedding,
            "metadata": metadata or {},
        },
        email_id=email_id,
        thread_id=thread_id,
        source=memory_type,
        metadata={"memory_type": memory_type, **(metadata or {})},
    )
    _upsert_semantic_memory_index(
        memory_type=memory_type,
        subject_id=subject_id,
        summary=summary,
        email_id=email_id,
        thread_id=thread_id,
        embedding=embedding,
        metadata=metadata or {},
    )
    return encrypted


def store_calendar_event(event: Any, *, source: str = "calendar") -> StoredRecord | None:
    payload = event.model_dump(mode="json") if hasattr(event, "model_dump") else dict(event)
    record_id = payload.get("id") or _stable_hash(json.dumps(payload, sort_keys=True))
    source_email = payload.get("source_email_id")
    metadata = {
        "title_hash": _stable_hash(payload.get("title", "")),
        "attendee_count": len(payload.get("attendees", []) or []),
        "source_email_id": source_email,
    }
    return upsert_record(
        "calendar_event",
        record_id=record_id,
        payload=payload,
        email_id=source_email,
        source=source,
        occurred_at=payload.get("start"),
        metadata=metadata,
    )


def load_calendar_events() -> list[dict[str, Any]]:
    """Return decrypted saved calendar event payloads."""
    if not storage_configured():
        return []
    _require_psycopg()

    sql = """
        SELECT ciphertext
        FROM encrypted_records
        WHERE record_type = 'calendar_event'
        ORDER BY occurred_at ASC
    """
    with psycopg.connect(_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [decrypt_payload(row[0], _encryption_key()) for row in rows]


def delete_calendar_event_record(event_id: str) -> int:
    """Delete a calendar event from storage by its ID."""
    if not storage_configured():
        return 0
    _require_psycopg()

    with psycopg.connect(_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM encrypted_records WHERE record_type = 'calendar_event' AND record_id = %s",
                (event_id,)
            )
            deleted = cur.rowcount
        conn.commit()
    return deleted


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


def load_record_payload(record_type: str, record_id: str) -> dict[str, Any] | None:
    """Fetch and decrypt a typed record by its stable id."""
    if not storage_configured():
        return None
    _require_psycopg()

    with psycopg.connect(_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ciphertext
                FROM encrypted_records
                WHERE record_type = %s AND record_id = %s
                """,
                (record_type, record_id),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return decrypt_payload(row[0], _encryption_key())


def storage_stats() -> dict[str, Any]:
    """Return row counts for the encrypted store and optional vector index."""
    if not storage_configured():
        return {"configured": False, "records": {}, "semantic_memories": 0}
    _require_psycopg()

    with psycopg.connect(_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT record_type, COUNT(*)
                FROM encrypted_records
                GROUP BY record_type
                ORDER BY record_type
                """
            )
            records = {record_type: count for record_type, count in cur.fetchall()}
            semantic_count = 0
            if _semantic_memory_index_exists(cur):
                cur.execute("SELECT COUNT(*) FROM semantic_memories")
                semantic_count = cur.fetchone()[0]
    return {
        "configured": True,
        "records": records,
        "semantic_memories": semantic_count,
    }


def delete_email_records(email_id: str) -> dict[str, int]:
    """Delete all encrypted/vector records tied to one email."""
    if not storage_configured():
        return {"encrypted_records": 0, "semantic_memories": 0}
    _require_psycopg()

    with psycopg.connect(_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM encrypted_records WHERE email_id = %s", (email_id,))
            encrypted_deleted = cur.rowcount
            semantic_deleted = 0
            if _semantic_memory_index_exists(cur):
                cur.execute("DELETE FROM semantic_memories WHERE email_id = %s", (email_id,))
                semantic_deleted = cur.rowcount
        conn.commit()
    return {
        "encrypted_records": encrypted_deleted,
        "semantic_memories": semantic_deleted,
    }


def delete_all_storage_records() -> dict[str, int]:
    """Delete all storage rows while keeping schema and extensions intact."""
    if not storage_configured():
        return {"encrypted_records": 0, "semantic_memories": 0}
    _require_psycopg()

    with psycopg.connect(_database_url()) as conn:
        with conn.cursor() as cur:
            semantic_deleted = 0
            if _semantic_memory_index_exists(cur):
                cur.execute("DELETE FROM semantic_memories")
                semantic_deleted = cur.rowcount
            cur.execute("DELETE FROM encrypted_records")
            encrypted_deleted = cur.rowcount
        conn.commit()
    return {
        "encrypted_records": encrypted_deleted,
        "semantic_memories": semantic_deleted,
    }


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


def safe_store_sync_state(state: Any) -> None:
    _enqueue(store_sync_state, state)


def safe_store_calendar_event(event: Any, *, source: str = "calendar") -> None:
    _enqueue(store_calendar_event, event, source=source)


def safe_delete_calendar_event_record(event_id: str) -> None:
    _enqueue(delete_calendar_event_record, event_id)


def safe_store_pii_mappings(email_id: str, purpose: str, mappings: list[Any]) -> None:
    _enqueue(store_pii_mappings, email_id, purpose, mappings)


def safe_store_thread_state(thread_id: str, payload: dict[str, Any]) -> None:
    _enqueue(store_thread_state, thread_id, payload)


def safe_store_semantic_memory(**kwargs: Any) -> None:
    _enqueue(store_semantic_memory, **kwargs)


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


def _init_pgvector() -> None:
    """Initialize optional pgvector structures without breaking plain Postgres."""
    try:
        with psycopg.connect(_database_url()) as conn:
            with conn.cursor() as cur:
                # ── Migrate VECTOR(1536) → VECTOR(384) if needed ───────
                # The old schema used 1536 dims (OpenAI-compatible). We now
                # use sentence-transformers/all-MiniLM-L6-v2 which is 384.
                try:
                    cur.execute("""
                        SELECT atttypmod FROM pg_attribute
                        WHERE attrelid = 'semantic_memories'::regclass
                          AND attname = 'embedding'
                    """)
                    row = cur.fetchone()
                    if row and row[0] == 1536:
                        log.info("migrating_vector_dimension", extra={
                            "from": 1536, "to": 384,
                        })
                        cur.execute("ALTER TABLE semantic_memories DROP COLUMN embedding")
                        cur.execute("ALTER TABLE semantic_memories ADD COLUMN embedding VECTOR(384)")
                        conn.commit()
                except Exception:
                    # Table doesn't exist yet — that's fine, CREATE below
                    conn.rollback()

                cur.execute(PGVECTOR_SQL)
            conn.commit()
    except Exception as exc:
        log.warning(
            "pgvector_unavailable",
            extra={"storage_enabled": True, "error": str(exc)},
        )


def _upsert_semantic_memory_index(
    *,
    memory_type: str,
    subject_id: str,
    summary: str,
    email_id: str | None,
    thread_id: str | None,
    embedding: list[float] | None,
    metadata: dict[str, Any],
) -> None:
    if not storage_configured():
        return
    try:
        with psycopg.connect(_database_url()) as conn:
            with conn.cursor() as cur:
                if not _semantic_memory_index_exists(cur):
                    return
                cur.execute(
                    """
                    INSERT INTO semantic_memories (
                        id, memory_type, subject_id, email_id, thread_id,
                        summary, embedding, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (memory_type, subject_id)
                    DO UPDATE SET
                        email_id = EXCLUDED.email_id,
                        thread_id = EXCLUDED.thread_id,
                        summary = EXCLUDED.summary,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                    """,
                    (
                        str(uuid4()),
                        memory_type,
                        subject_id,
                        email_id,
                        thread_id,
                        summary,
                        embedding,
                        Jsonb(metadata),
                    ),
                )
            conn.commit()
    except Exception:
        log.exception(
            "semantic_memory_index_failed",
            extra={"storage_enabled": True, "storage_event": memory_type},
        )


def _semantic_memory_index_exists(cur: Any) -> bool:
    cur.execute("SELECT to_regclass('public.semantic_memories')")
    return cur.fetchone()[0] is not None


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
