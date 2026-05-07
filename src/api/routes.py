"""API routes for the email agent."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from src.config import get_settings
from src.connectors.mock import load_emails
from src.models.email import CalendarEvent, Classification, DraftReply, Email
from src.services import classifier, drafter
from src.services.calendar import get_upcoming_events, load_events

log = logging.getLogger(__name__)

router = APIRouter()

# ---- In-memory stores (initialised lazily) --------------------------------

_emails: dict[str, Email] = {}
_calendar: list[CalendarEvent] = []


def _ensure_loaded() -> None:
    """Populate the in-memory stores on first access."""
    if not _emails:
        for email in load_emails(get_settings().data_dir / "seed_emails.json"):
            _emails[email.id] = email
    if not _calendar:
        _calendar.extend(load_events(get_settings().data_dir / "calendar.json"))


def _get_email(email_id: str) -> Email:
    _ensure_loaded()
    email = _emails.get(email_id)
    if email is None:
        raise HTTPException(status_code=404, detail=f"Email {email_id} not found")
    return email


def _relevant_events(email: Email) -> list[CalendarEvent]:
    return get_upcoming_events(_calendar, email.timestamp)


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
async def classify_email(email_id: str) -> dict[str, Any]:
    """Classify an email by priority and category."""
    email = _get_email(email_id)
    result = await classifier.classify(email, _relevant_events(email))
    email.classification = result
    return result.model_dump(mode="json")


@router.post("/emails/{email_id}/draft")
async def draft_email_reply(email_id: str) -> dict[str, Any]:
    """Generate a draft reply for an email.

    The email must be classified first.
    """
    email = _get_email(email_id)
    if email.classification is None:
        raise HTTPException(
            status_code=400,
            detail="Classify the email before drafting a reply.",
        )
    result = await drafter.draft_reply(
        email, email.classification, _relevant_events(email)
    )
    email.draft_reply = result
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
    # In a real system, this would send the email.
    email.draft_reply = None
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
            results.append({
                "email_id": email.id,
                "classification": result.model_dump(mode="json"),
            })
    return results


@router.get("/calendar")
async def get_calendar() -> list[dict[str, Any]]:
    """Return mock calendar events."""
    _ensure_loaded()
    return [ev.model_dump(mode="json") for ev in _calendar]
