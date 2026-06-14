"""Semantic search over email history using fastembed + pgvector.

Uses ``fastembed`` with the ``all-MiniLM-L6-v2`` ONNX model for lightweight,
fast embedding generation (384 dimensions). No PyTorch dependency required.

Provides:
  - ``generate_embedding(text)`` — generate a 384-dim embedding vector
  - ``search_similar_emails(query, limit)`` — cosine similarity search
  - ``get_thread_context(thread_id)`` — summarize thread history
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:
    psycopg = None  # type: ignore[assignment]
    Jsonb = None  # type: ignore[assignment]

from src.storage import storage_configured

# ── Embedding model (lazy-loaded singleton) ────────────────────────────────

_embedding_model = None


def _get_embedding_model():
    """Lazy-load the fastembed model."""
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model
    try:
        from fastembed import TextEmbedding
        _embedding_model = TextEmbedding(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
        )
        log.info("embedding_model_loaded", extra={"model": "all-MiniLM-L6-v2", "dims": 384})
        return _embedding_model
    except ImportError:
        log.warning("fastembed_not_installed — semantic search disabled")
        return None
    except Exception:
        log.exception("embedding_model_load_failed")
        return None


# ── Embedding generation ──────────────────────────────────────────────────


def generate_embedding(text: str) -> list[float] | None:
    """Generate a 384-dimensional embedding for the given text.

    Returns None if fastembed is not installed or the model fails to load.
    """
    if not text or not text.strip():
        return None
    model = _get_embedding_model()
    if model is None:
        return None
    try:
        # fastembed returns a generator; take the first result
        embeddings = list(model.embed([text[:512]]))  # cap at 512 chars for speed
        if embeddings:
            return embeddings[0].tolist()
        return None
    except Exception:
        log.exception("embedding_generation_failed")
        return None


# ── Semantic search ───────────────────────────────────────────────────────


def search_similar_emails(
    query: str,
    *,
    limit: int = 5,
    memory_type: str = "email_summary",
) -> list[dict[str, Any]]:
    """Find semantically similar emails using cosine distance.

    Returns a list of dicts with: email_id, thread_id, summary, distance.
    """
    if not storage_configured():
        return []

    query_embedding = generate_embedding(query)
    if query_embedding is None:
        return []

    try:
        with psycopg.connect(_database_url()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT email_id, thread_id, summary,
                           embedding <=> %s::vector AS distance
                    FROM semantic_memories
                    WHERE memory_type = %s
                      AND embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (
                        str(query_embedding),
                        memory_type,
                        str(query_embedding),
                        limit,
                    ),
                )
                return [
                    {
                        "email_id": row[0],
                        "thread_id": row[1],
                        "summary": row[2],
                        "distance": float(row[3]),
                    }
                    for row in cur.fetchall()
                ]
    except Exception:
        log.exception("semantic_search_failed")
        return []


def get_thread_context(thread_id: str) -> str:
    """Get all email summaries for a given thread, concatenated."""
    if not storage_configured():
        return ""
    try:
        with psycopg.connect(_database_url()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT summary FROM semantic_memories
                    WHERE thread_id = %s AND memory_type = 'email_summary'
                    ORDER BY created_at ASC
                    """,
                    (thread_id,),
                )
                summaries = [row[0] for row in cur.fetchall()]
                return "\n---\n".join(summaries) if summaries else ""
    except Exception:
        log.exception("get_thread_context_failed")
        return ""


# ── Helpers ────────────────────────────────────────────────────────────────


def _database_url() -> str:
    return os.environ["DATABASE_URL"]
