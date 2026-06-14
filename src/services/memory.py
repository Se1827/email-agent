"""Memory & personalization service — sender profiles and user preferences.

Provides database-backed storage for:
  - Sender profiles: track relationships, interaction frequency, VIP status
  - User preferences: standing instructions, scheduling constraints
  - Preference-aware context for classification and drafting

All functions gracefully degrade to no-ops when storage is not configured.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

log = logging.getLogger(__name__)

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:
    psycopg = None  # type: ignore[assignment]
    Jsonb = None  # type: ignore[assignment]

from src.storage import storage_configured


# ── Data classes ───────────────────────────────────────────────────────────


@dataclass
class SenderProfile:
    """Profile for a known email sender."""
    email_address: str
    display_name: str = ""
    relationship: str = "unknown"  # colleague, manager, client, external, unknown
    tone_preference: str = "professional"
    avg_priority: str = "normal"
    interaction_count: int = 0
    last_interaction: Optional[datetime] = None
    is_vip: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Preference:
    """A single user preference / standing instruction."""
    id: str
    pref_type: str  # scheduling_constraint, drafting_instruction, general
    pref_key: str
    pref_value: str
    is_active: bool = True


# ── Sender profiles ───────────────────────────────────────────────────────


def get_sender_profile(email_address: str) -> SenderProfile | None:
    """Retrieve a sender profile from the database."""
    if not storage_configured():
        return None
    try:
        with psycopg.connect(_database_url()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT email_address, display_name, relationship, "
                    "tone_preference, avg_priority, interaction_count, "
                    "last_interaction, is_vip, metadata "
                    "FROM sender_profiles WHERE email_address = %s",
                    (email_address.lower(),),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return SenderProfile(
                    email_address=row[0],
                    display_name=row[1] or "",
                    relationship=row[2] or "unknown",
                    tone_preference=row[3] or "professional",
                    avg_priority=row[4] or "normal",
                    interaction_count=row[5] or 0,
                    last_interaction=row[6],
                    is_vip=row[7] or False,
                    metadata=row[8] or {},
                )
    except Exception:
        log.exception("get_sender_profile_failed", extra={"email_address": email_address})
        return None


def upsert_sender_profile(
    email_address: str,
    *,
    display_name: str | None = None,
    relationship: str | None = None,
    tone_preference: str | None = None,
    avg_priority: str | None = None,
    is_vip: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Create or update a sender profile."""
    if not storage_configured():
        return
    try:
        with psycopg.connect(_database_url()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sender_profiles (
                        email_address, display_name, relationship,
                        tone_preference, avg_priority, is_vip, metadata,
                        interaction_count, last_interaction
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 1, NOW())
                    ON CONFLICT (email_address) DO UPDATE SET
                        display_name = COALESCE(EXCLUDED.display_name, sender_profiles.display_name),
                        relationship = COALESCE(EXCLUDED.relationship, sender_profiles.relationship),
                        tone_preference = COALESCE(EXCLUDED.tone_preference, sender_profiles.tone_preference),
                        avg_priority = COALESCE(EXCLUDED.avg_priority, sender_profiles.avg_priority),
                        is_vip = COALESCE(EXCLUDED.is_vip, sender_profiles.is_vip),
                        metadata = COALESCE(EXCLUDED.metadata, sender_profiles.metadata),
                        interaction_count = sender_profiles.interaction_count + 1,
                        last_interaction = NOW(),
                        updated_at = NOW()
                    """,
                    (
                        email_address.lower(),
                        display_name,
                        relationship,
                        tone_preference,
                        avg_priority,
                        is_vip,
                        Jsonb(metadata) if metadata else None,
                    ),
                )
            conn.commit()
    except Exception:
        log.exception("upsert_sender_profile_failed", extra={"email_address": email_address})


def update_profile_from_classification(
    email_address: str,
    priority: str,
    *,
    display_name: str | None = None,
) -> None:
    """Auto-update a sender profile after classification.

    Tracks interaction frequency and maintains a running average priority.
    Called from the classify endpoint after each successful classification.
    """
    upsert_sender_profile(
        email_address,
        display_name=display_name,
        avg_priority=priority,
    )


def get_vip_senders() -> list[str]:
    """Return email addresses of all VIP senders from the database."""
    if not storage_configured():
        return []
    try:
        with psycopg.connect(_database_url()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT email_address FROM sender_profiles WHERE is_vip = TRUE",
                )
                return [row[0] for row in cur.fetchall()]
    except Exception:
        log.exception("get_vip_senders_failed")
        return []


# ── User preferences ──────────────────────────────────────────────────────


def store_preference(
    pref_type: str,
    pref_key: str,
    pref_value: str,
) -> str:
    """Store a user preference. Returns the preference ID."""
    pref_id = str(uuid4())
    if not storage_configured():
        return pref_id
    try:
        with psycopg.connect(_database_url()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_preferences (id, pref_type, pref_key, pref_value)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (pref_type, pref_key) DO UPDATE SET
                        pref_value = EXCLUDED.pref_value,
                        is_active = TRUE
                    RETURNING id
                    """,
                    (pref_id, pref_type, pref_key, pref_value),
                )
                result = cur.fetchone()
                if result:
                    pref_id = str(result[0])
            conn.commit()
    except Exception:
        log.exception("store_preference_failed")
    return pref_id


def get_preferences(pref_type: str | None = None) -> list[Preference]:
    """Retrieve user preferences, optionally filtered by type."""
    if not storage_configured():
        return []
    try:
        with psycopg.connect(_database_url()) as conn:
            with conn.cursor() as cur:
                if pref_type:
                    cur.execute(
                        "SELECT id, pref_type, pref_key, pref_value, is_active "
                        "FROM user_preferences WHERE pref_type = %s AND is_active = TRUE",
                        (pref_type,),
                    )
                else:
                    cur.execute(
                        "SELECT id, pref_type, pref_key, pref_value, is_active "
                        "FROM user_preferences WHERE is_active = TRUE",
                    )
                return [
                    Preference(
                        id=str(row[0]),
                        pref_type=row[1],
                        pref_key=row[2],
                        pref_value=row[3],
                        is_active=row[4],
                    )
                    for row in cur.fetchall()
                ]
    except Exception:
        log.exception("get_preferences_failed")
        return []


def delete_preference(pref_id: str) -> bool:
    """Soft-delete a preference by ID."""
    if not storage_configured():
        return False
    try:
        with psycopg.connect(_database_url()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE user_preferences SET is_active = FALSE WHERE id = %s::uuid",
                    (pref_id,),
                )
                deleted = cur.rowcount > 0
            conn.commit()
            return deleted
    except Exception:
        log.exception("delete_preference_failed")
        return False


def get_scheduling_constraints() -> list[str]:
    """Return active scheduling constraint values for calendar intelligence."""
    prefs = get_preferences("scheduling_constraint")
    return [p.pref_value for p in prefs]


# ── Helpers ────────────────────────────────────────────────────────────────


def _database_url() -> str:
    return os.environ["DATABASE_URL"]
