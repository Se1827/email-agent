"""Action item extraction and management.

Extracts actionable tasks from classified emails using a single LLM call.
Stores and tracks action items in the database with status lifecycle:
  pending → in_progress → completed | dismissed

Provides:
  - ``extract_action_items(email)`` — LLM-powered extraction
  - ``get_action_items(status)`` — query stored action items
  - ``update_action_item(id, status)`` — lifecycle management
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.llm import client as llm

log = logging.getLogger(__name__)

try:
    import psycopg
except ImportError:
    psycopg = None  # type: ignore[assignment]

from src.storage import storage_configured


# ── LLM prompt for action item extraction ──────────────────────────────────

_EXTRACT_SYSTEM = """\
You are an email assistant that extracts action items from emails.
An action item is a specific task that the email recipient needs to do.

Rules:
1. Only extract items that require ACTION from the recipient.
2. Be specific and concise — each item should be one actionable sentence.
3. Include due dates if mentioned (as ISO 8601 format).
4. Do NOT include FYI-only information or context.
5. If no action items exist, return an empty list.

Respond ONLY with a JSON array (no markdown, no extra text):
[
  {"description": "...", "due_date": "2026-06-15T17:00:00Z" or null}
]
"""

_EXTRACT_USER = """\
From: {sender}
Subject: {subject}
Date: {timestamp}

{body}
"""


# ── Action item extraction ─────────────────────────────────────────────────


async def extract_action_items(
    email_id: str,
    sender: str,
    subject: str,
    body: str,
    timestamp: str,
    *,
    thread_id: str | None = None,
) -> list[dict[str, Any]]:
    """Extract action items from an email using a single LLM call.

    Returns a list of dicts: [{"id", "description", "due_date", "status"}]
    """
    user_msg = _EXTRACT_USER.format(
        sender=sender,
        subject=subject,
        timestamp=timestamp,
        body=body[:2000],  # cap body for token efficiency
    )

    try:
        raw = await llm.chat(
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            max_tokens=500,
        )

        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])

        items = json.loads(text)
        if not isinstance(items, list):
            return []

        results = []
        for item in items:
            desc = item.get("description", "").strip()
            if not desc:
                continue
            due = item.get("due_date")
            action_id = str(uuid4())

            # Store in DB
            _store_action_item(
                action_id=action_id,
                email_id=email_id,
                thread_id=thread_id,
                description=desc,
                due_date=due,
            )
            results.append({
                "id": action_id,
                "email_id": email_id,
                "description": desc,
                "due_date": due,
                "status": "pending",
            })

        log.info(
            "action_items_extracted",
            extra={
                "email_id": email_id,
                "count": len(results),
            },
        )
        return results

    except Exception:
        log.exception("action_item_extraction_failed", extra={"email_id": email_id})
        return []


# ── Database operations ────────────────────────────────────────────────────


def _store_action_item(
    *,
    action_id: str,
    email_id: str,
    thread_id: str | None,
    description: str,
    due_date: str | None,
) -> None:
    """Store an action item in the database."""
    if not storage_configured():
        return
    try:
        with psycopg.connect(_database_url()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO action_items (id, email_id, thread_id, description, due_date)
                    VALUES (%s::uuid, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        action_id,
                        email_id,
                        thread_id,
                        description,
                        due_date,
                    ),
                )
            conn.commit()
    except Exception:
        log.exception("store_action_item_failed")


def get_action_items(
    status: str | None = None,
    email_id: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve action items, optionally filtered by status or email_id."""
    if not storage_configured():
        return []
    try:
        with psycopg.connect(_database_url()) as conn:
            with conn.cursor() as cur:
                conditions = []
                params: list[Any] = []

                if status:
                    conditions.append("status = %s")
                    params.append(status)
                if email_id:
                    conditions.append("email_id = %s")
                    params.append(email_id)

                where = ""
                if conditions:
                    where = "WHERE " + " AND ".join(conditions)

                cur.execute(
                    f"""
                    SELECT id, email_id, thread_id, description,
                           due_date, status, extracted_at, completed_at
                    FROM action_items {where}
                    ORDER BY extracted_at DESC
                    LIMIT 100
                    """,
                    params,
                )
                return [
                    {
                        "id": str(row[0]),
                        "email_id": row[1],
                        "thread_id": row[2],
                        "description": row[3],
                        "due_date": row[4].isoformat() if row[4] else None,
                        "status": row[5],
                        "extracted_at": row[6].isoformat() if row[6] else None,
                        "completed_at": row[7].isoformat() if row[7] else None,
                    }
                    for row in cur.fetchall()
                ]
    except Exception:
        log.exception("get_action_items_failed")
        return []


def update_action_item(action_id: str, status: str) -> bool:
    """Update an action item's status. Returns True if updated."""
    valid_statuses = {"pending", "in_progress", "completed", "dismissed"}
    if status not in valid_statuses:
        return False
    if not storage_configured():
        return False
    try:
        completed_at = "NOW()" if status == "completed" else "NULL"
        with psycopg.connect(_database_url()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE action_items
                    SET status = %s,
                        completed_at = {completed_at}
                    WHERE id = %s::uuid
                    """,
                    (status, action_id),
                )
                updated = cur.rowcount > 0
            conn.commit()
            return updated
    except Exception:
        log.exception("update_action_item_failed")
        return False


def _database_url() -> str:
    return os.environ["DATABASE_URL"]
