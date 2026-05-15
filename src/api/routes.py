"""API routes for the email agent."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.config import get_settings
from src.connectors.mock import load_emails as load_mock_emails
from src.connectors.imap import fetch_emails as fetch_imap_emails
from src.models.email import CalendarEvent, Classification, DraftReply, Email
from src.services import classifier, drafter
from src.services.calendar import get_upcoming_events, load_events
from src.services.pii import PrivacyGateway
from src.storage import (
    delete_all_storage_records,
    delete_email_records,
    load_email_state,
    safe_record_event,
    safe_store_calendar_event,
    safe_store_email,
    safe_store_semantic_memory,
    safe_store_thread_state,
    storage_stats,
    store_email,
)

log = logging.getLogger(__name__)

router = APIRouter()

# ---- In-memory stores (initialised lazily) --------------------------------

_emails: dict[str, Email] = {}
_calendar: list[CalendarEvent] = []


def _load_email_source() -> list[Email]:
    """Load emails from the configured source (mock JSON or IMAP)."""
    cfg = get_settings()
    if cfg.email_source == "imap":
        return fetch_imap_emails(
            host=cfg.imap_host,
            port=cfg.imap_port,
            username=cfg.imap_user,
            password=cfg.imap_pass,
            mailbox=cfg.imap_mailbox,
            limit=cfg.imap_fetch_limit,
            use_ssl=cfg.imap_use_ssl,
        )
    return load_mock_emails(cfg.data_dir / "seed_emails.json")


def _ensure_loaded() -> None:
    """Populate the in-memory stores on first access."""
    if not _emails:
        try:
            source = get_settings().email_source
            for email in _load_email_source():
                _hydrate_email_state(email)
                _emails[email.id] = email
                safe_store_email(email, source=source)
                _store_email_memory(email)
        except Exception as exc:
            log.error("email_load_failed", extra={"error": str(exc)})
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Failed to load emails: {exc}. "
                    "Check your EMAIL_SOURCE and IMAP settings in .env."
                ),
            )
    if not _calendar:
        _calendar.extend(load_events(get_settings().data_dir / "calendar.json"))
        for event in _calendar:
            safe_store_calendar_event(event, source="mock")


def _get_email(email_id: str) -> Email:
    _ensure_loaded()
    email = _emails.get(email_id)
    if email is None:
        raise HTTPException(status_code=404, detail=f"Email {email_id} not found")
    return email


def _relevant_events(email: Email) -> list[CalendarEvent]:
    return get_upcoming_events(_calendar, email.timestamp)


def _hydrate_email_state(email: Email) -> None:
    """Apply cached workflow state from encrypted storage onto source emails."""
    stored = load_email_state(email.id)
    if not stored:
        return
    try:
        cached = Email.model_validate(stored)
    except Exception:
        log.exception("email_cache_hydration_failed", extra={"email_id": email.id})
        return
    email.classification = cached.classification
    email.draft_reply = cached.draft_reply


def _persist_email_state(email: Email, *, source: str = "workflow") -> None:
    """Persist the latest email workflow state immediately and via audit records."""
    try:
        store_email(email, source=source)
    except Exception:
        log.exception("email_state_persist_failed", extra={"email_id": email.id})
    _store_thread_state(email)
    _store_email_memory(email)


def _store_thread_state(email: Email) -> None:
    classification = email.classification
    participants = sorted({email.sender, *email.recipients})
    thread_id = email.thread_id or email.id
    pending_action = "reply_or_follow_up" if classification and classification.priority.value in {"critical", "high"} else None
    payload = {
        "thread_id": thread_id,
        "last_email_id": email.id,
        "participants": participants,
        "topic": email.subject,
        "priority": classification.priority.value if classification else None,
        "category": classification.category.value if classification else None,
        "last_sentiment": _sentiment_hint(email.body),
        "pending_action": pending_action,
        "has_draft": email.draft_reply is not None,
        "updated_from": "api",
    }
    safe_store_thread_state(thread_id, payload)


def _store_email_memory(email: Email) -> None:
    compact_body = " ".join(email.body.split())[:500]
    summary = PrivacyGateway().mask_text(compact_body).text
    safe_store_semantic_memory(
        memory_type="email_summary",
        subject_id=email.id,
        email_id=email.id,
        thread_id=email.thread_id or email.id,
        summary=summary,
        metadata={
            "subject_chars": len(email.subject),
            "has_classification": email.classification is not None,
            "has_draft": email.draft_reply is not None,
        },
    )


def _sentiment_hint(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("urgent", "frustrated", "blocked", "escalat", "asap")):
        return "urgent"
    if any(word in lowered for word in ("thanks", "appreciate", "great", "happy")):
        return "positive"
    return "neutral"


# ---- Endpoints -------------------------------------------------------------


@router.get("/emails")
async def list_emails() -> list[dict[str, Any]]:
    """Return all emails with their current classification (if any)."""
    _ensure_loaded()
    return [email.model_dump(mode="json") for email in _emails.values()]


@router.get("/emails/{email_id}")
async def get_email(email_id: str) -> dict[str, Any]:
    """Return a single email with full detail."""
    return _get_email(email_id).model_dump(mode="json")


@router.post("/emails/{email_id}/classify")
async def classify_email(
    email_id: str,
    force: bool = Query(False, description="Re-run the model even if cached"),
) -> dict[str, Any]:
    """Classify an email by priority and category."""
    email = _get_email(email_id)
    if email.classification is not None and not force:
        safe_record_event(
            "email.classification_cache_hit",
            {"classification": email.classification.model_dump(mode="json")},
            subject_id=email.id,
        )
        return email.classification.model_dump(mode="json")
    result = await classifier.classify(email, _relevant_events(email))
    email.classification = result
    safe_record_event(
        "email.classified",
        {
            "classification": result.model_dump(mode="json"),
            "subject": email.subject,
            "sender": email.sender,
        },
        subject_id=email.id,
    )
    _persist_email_state(email)
    return result.model_dump(mode="json")


@router.post("/emails/{email_id}/draft")
async def draft_email_reply(
    email_id: str,
    force: bool = Query(False, description="Re-run the model even if cached"),
) -> dict[str, Any]:
    """Generate a draft reply for an email.

    The email must be classified first.
    """
    email = _get_email(email_id)
    if email.classification is None:
        raise HTTPException(
            status_code=400,
            detail="Classify the email before drafting a reply.",
        )
    if email.draft_reply is not None and not force:
        safe_record_event(
            "email.draft_cache_hit",
            {"draft_reply": email.draft_reply.model_dump(mode="json")},
            subject_id=email.id,
        )
        return email.draft_reply.model_dump(mode="json")
    result = await drafter.draft_reply(
        email, email.classification, _relevant_events(email)
    )
    email.draft_reply = result
    safe_record_event(
        "email.drafted",
        {
            "classification": email.classification.model_dump(mode="json"),
            "draft_reply": result.model_dump(mode="json"),
            "subject": email.subject,
            "sender": email.sender,
        },
        subject_id=email.id,
    )
    _persist_email_state(email)
    return result.model_dump(mode="json")


@router.post("/emails/{email_id}/approve")
async def approve_draft(email_id: str) -> dict[str, str]:
    """Approve the current draft reply (simulated send)."""
    email = _get_email(email_id)
    if email.draft_reply is None:
        raise HTTPException(
            status_code=400,
            detail="No draft to approve. Generate a draft first.",
        )
    log.info("draft_approved", extra={"email_id": email_id})
    body_preview = email.draft_reply.body[:80]
    safe_record_event(
        "email.approved",
        {"preview": body_preview},
        subject_id=email.id,
    )
    # In a real system, this would send the email.
    email.draft_reply = None
    _persist_email_state(email)
    return {"status": "sent", "preview": body_preview}


@router.post("/emails/classify-all")
async def classify_all() -> list[dict[str, Any]]:
    """Batch-classify all emails that have not been classified yet."""
    _ensure_loaded()
    results = []
    for email in _emails.values():
        if email.classification is None:
            result = await classifier.classify(email, _relevant_events(email))
            email.classification = result
            safe_record_event(
                "email.classified",
                {
                    "classification": result.model_dump(mode="json"),
                    "subject": email.subject,
                    "sender": email.sender,
                },
                subject_id=email.id,
            )
            results.append({
                "email_id": email.id,
                "classification": result.model_dump(mode="json"),
            })
            _persist_email_state(email)
    return results


@router.get("/calendar")
async def get_calendar() -> list[dict[str, Any]]:
    """Return mock calendar events."""
    _ensure_loaded()
    return [ev.model_dump(mode="json") for ev in _calendar]


@router.post("/emails/refresh")
async def refresh_emails() -> dict[str, Any]:
    """Clear the in-memory email store and re-fetch from the source.

    Useful when using IMAP to pull new mail without restarting the server.
    """
    _emails.clear()
    _ensure_loaded()
    return {"status": "refreshed", "count": len(_emails)}


@router.get("/storage/stats")
async def get_storage_stats() -> dict[str, Any]:
    """Return current storage row counts."""
    return storage_stats()


@router.delete("/storage/emails/{email_id}")
async def wipe_email_storage(email_id: str) -> dict[str, Any]:
    """Delete storage rows for one email and reset in-memory state."""
    deleted = delete_email_records(email_id)
    if email_id in _emails:
        _emails[email_id].classification = None
        _emails[email_id].draft_reply = None
    return {"status": "deleted", "email_id": email_id, "deleted": deleted}


@router.delete("/storage")
async def wipe_all_storage() -> dict[str, Any]:
    """Delete all storage rows and reset in-memory workflow state."""
    deleted = delete_all_storage_records()
    for email in _emails.values():
        email.classification = None
        email.draft_reply = None
    return {"status": "deleted", "deleted": deleted}

