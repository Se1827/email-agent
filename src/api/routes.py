"""API routes for the email agent."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.config import get_settings
from src.connectors.mock import load_emails as load_mock_emails
from src.connectors.imap import fetch_emails as fetch_imap_emails
from src.models.email import (
    AccountConfig,
    CalendarEvent,
    Classification,
    DashboardStats,
    DraftQuality,
    DraftReply,
    Email,
    Notification,
)
from src.services import classifier, drafter
from src.services.accounts import (
    account_inbox,
    get_account,
    load_accounts,
    list_accounts_summary,
    save_accounts,
)
from src.services.calendar import (
    create_event,
    delete_event,
    format_calendar_context,
    get_upcoming_events,
    load_events,
    update_event,
)
from src.services.inbox_identity import canonicalize_inbox
from src.services.pii import PrivacyGateway
from src.storage import (
    delete_all_storage_records,
    delete_email_records,
    email_content_hash,
    load_email_states,
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
_notifications: list[Notification] = []
_activity_log: list[dict[str, Any]] = []


def _log_activity(action: str, detail: str, related_id: str | None = None) -> None:
    """Append an entry to the in-memory activity feed."""
    _activity_log.insert(0, {
        "id": uuid4().hex[:8],
        "action": action,
        "detail": detail,
        "related_id": related_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    if len(_activity_log) > 50:
        _activity_log[:] = _activity_log[:50]


def _generate_notifications() -> None:
    """Build smart notifications from current email + calendar state."""
    _notifications.clear()
    now = datetime.now(timezone.utc)

    # Urgent unresponded emails
    urgent_count = sum(
        1 for e in _emails.values()
        if e.classification
        and e.classification.priority.value in ("critical", "high")
        and not e.draft_reply
        and not e.is_read
    )
    if urgent_count > 0:
        _notifications.append(Notification(
            id=f"notif-urgent-{uuid4().hex[:6]}",
            type="urgent_email",
            title="Urgent emails need attention",
            message=f"{urgent_count} {'email needs' if urgent_count == 1 else 'emails need'} a response",
            severity="critical",
            timestamp=now,
        ))

    # Upcoming deadlines (next 48h)
    for ev in _calendar:
        hours_until = (ev.start.replace(tzinfo=timezone.utc) - now).total_seconds() / 3600
        if 0 < hours_until < 48:
            sev = "critical" if hours_until < 6 else "warning" if hours_until < 24 else "info"
            _notifications.append(Notification(
                id=f"notif-cal-{ev.id}",
                type="deadline" if ev.is_all_day else "meeting_soon",
                title=f"{'Deadline' if ev.is_all_day else 'Upcoming'}: {ev.title}",
                message=f"In {int(hours_until)} hours" if hours_until >= 1 else "Less than 1 hour away",
                severity=sev,
                related_id=ev.id,
                related_type="event",
                timestamp=now,
            ))

    # Unclassified emails insight
    unclassified = sum(1 for e in _emails.values() if not e.classification)
    if unclassified > 0:
        _notifications.append(Notification(
            id=f"notif-unclassified-{uuid4().hex[:6]}",
            type="ai_insight",
            title="Emails awaiting AI triage",
            message=f"{unclassified} {'email has' if unclassified == 1 else 'emails have'} not been classified yet",
            severity="info",
            timestamp=now,
        ))


def _load_email_source() -> list[Email]:
    """Load emails from every active configured account."""
    cfg = get_settings()
    emails: list[Email] = []
    for account in load_accounts(cfg.data_dir):
        if not account.is_active:
            continue
        inbox = account_inbox(account)
        source_emails = _load_account_email_source(account, inbox)
        for email in source_emails:
            _stamp_account_email(email, account, inbox)
        emails.extend(source_emails)
    return emails


def _load_account_email_source(account: AccountConfig, inbox: str) -> list[Email]:
    cfg = get_settings()
    if account.provider == "mock":
        return load_mock_emails(cfg.data_dir / "seed_emails.json")
    return fetch_imap_emails(
        host=account.imap_host or cfg.imap_host,
        port=account.imap_port or cfg.imap_port,
        username=account.imap_user or account.email or cfg.imap_user,
        password=account.imap_pass or cfg.imap_pass,
        mailbox=account.imap_mailbox or cfg.imap_mailbox,
        limit=cfg.imap_fetch_limit,
        use_ssl=account.imap_use_ssl,
        inbox=inbox,
    )


def _stamp_account_email(email: Email, account: AccountConfig, inbox: str) -> None:
    email.account_id = account.id
    email.inbox = inbox
    if not email.id.startswith(f"{account.id}:"):
        email.id = f"{account.id}:{email.id}"
    if email.thread_id and not email.thread_id.startswith(f"{account.id}:"):
        email.thread_id = f"{account.id}:{email.thread_id}"


def _ensure_loaded() -> None:
    """Populate the in-memory stores on first access."""
    if not _emails:
        try:
            cfg = get_settings()
            load_mode = _normalize_email_load_mode(cfg.email_load_mode)
            if load_mode in {"db_then_source", "db_only"}:
                for account in load_accounts(cfg.data_dir):
                    if account.is_active:
                        _load_emails_from_storage(account_inbox(account), account=account)
            if load_mode != "db_only":
                for email in _load_email_source():
                    _merge_source_email(email, source=email.account_id or cfg.email_source)
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


def _load_emails_from_storage(inbox: str, *, account: AccountConfig | None = None) -> None:
    for payload in load_email_states(inbox=inbox):
        try:
            email = Email.model_validate(payload)
        except Exception:
            log.exception("stored_email_load_failed")
            continue
        if account is not None and not email.account_id:
            email.account_id = account.id
            email.inbox = inbox
        email.storage_origin = "db"
        _emails[email.id] = email
        _store_email_memory(email)


def _merge_source_email(email: Email, *, source: str) -> None:
    """Merge a fresh source email into DB-seeded inbox state."""
    email.inbox = email.inbox or _current_inbox()
    cached = _emails.get(email.id)
    if cached is None and email.account_id and email.id.startswith(f"{email.account_id}:"):
        legacy_id = email.id.split(":", 1)[1]
        cached = _emails.pop(legacy_id, None)
    if cached is None:
        _hydrate_email_state(email)
        email.storage_origin = "source+cache" if email.classification or email.draft_reply else "source"
    elif email_content_hash(email) == email_content_hash(cached):
        email.classification = cached.classification
        email.draft_reply = cached.draft_reply
        email.is_read = cached.is_read
        email.is_starred = cached.is_starred
        email.labels = cached.labels
        email.storage_origin = "source+cache"
    else:
        safe_record_event(
            "email.source_updated",
            {
                "previous_content_hash": email_content_hash(cached),
                "new_content_hash": email_content_hash(email),
                "source": source,
            },
            subject_id=email.id,
        )
        email.storage_origin = "source-updated"
    _emails[email.id] = email
    safe_store_email(email, source=source)
    _store_email_memory(email)


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
    stored = load_email_state(email.id, inbox=email.inbox or _current_inbox())
    if not stored:
        return
    try:
        cached = Email.model_validate(stored)
    except Exception:
        log.exception("email_cache_hydration_failed", extra={"email_id": email.id})
        return
    email.classification = cached.classification
    email.draft_reply = cached.draft_reply
    email.is_read = cached.is_read
    email.is_starred = cached.is_starred
    email.labels = cached.labels
    email.storage_origin = "source+cache"


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


def _normalize_email_load_mode(mode: str) -> str:
    normalized = mode.strip().lower().replace("-", "_")
    if normalized in {"source", "source_only"}:
        return "source_only"
    if normalized in {"db", "db_only", "cache_only"}:
        return "db_only"
    return "db_then_source"


def _current_inbox() -> str:
    cfg = get_settings()
    accounts = [account for account in load_accounts(cfg.data_dir) if account.is_active]
    if accounts:
        return account_inbox(accounts[0])
    return canonicalize_inbox(cfg.imap_user, fallback=f"imap:{cfg.imap_host}:{cfg.imap_mailbox}")


# ---- Email Endpoints -------------------------------------------------------


@router.get("/emails")
async def list_emails(
    account_id: str | None = Query(None, description="Filter by account ID"),
) -> list[dict[str, Any]]:
    """Return all emails with their current classification (if any)."""
    _ensure_loaded()
    emails = list(_emails.values())
    if account_id:
        emails = [e for e in emails if e.account_id == account_id]
    return [email.model_dump(mode="json") for email in emails]


@router.get("/emails/{email_id}")
async def get_email(email_id: str) -> dict[str, Any]:
    """Return a single email with full detail."""
    return _get_email(email_id).model_dump(mode="json")


@router.get("/emails/{email_id}/thread")
async def get_email_thread(email_id: str) -> list[dict[str, Any]]:
    """Return all emails sharing the same thread_id."""
    _ensure_loaded()
    email = _get_email(email_id)
    thread_id = email.thread_id or email.id
    thread = [
        e.model_dump(mode="json")
        for e in _emails.values()
        if (e.thread_id or e.id) == thread_id
    ]
    thread.sort(key=lambda e: e.get("timestamp", ""))
    return thread


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
    _log_activity(
        "classified",
        f"Email from {email.sender.split('@')[0]} classified as {result.priority.value.upper()}",
        email.id,
    )
    _persist_email_state(email)
    return result.model_dump(mode="json")


class DraftRequest(BaseModel):
    quality: str = "balanced"


@router.post("/emails/{email_id}/draft")
async def draft_email_reply(
    email_id: str,
    body: DraftRequest | None = None,
    force: bool = Query(False, description="Re-run the model even if cached"),
) -> dict[str, Any]:
    """Generate a draft reply for an email.

    The email must be classified first.
    """
    email = _get_email(email_id)
    quality = (body.quality if body else None) or get_settings().default_draft_quality
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
    result.quality = quality
    email.draft_reply = result
    safe_record_event(
        "email.drafted",
        {
            "classification": email.classification.model_dump(mode="json"),
            "draft_reply": result.model_dump(mode="json"),
            "subject": email.subject,
            "sender": email.sender,
            "quality": quality,
        },
        subject_id=email.id,
    )
    _log_activity("drafted", f"Draft reply generated for '{email.subject[:40]}'", email.id)
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
    _log_activity("approved", f"Draft reply approved for '{email.subject[:40]}'", email.id)
    # In a real system, this would send the email.
    email.draft_reply = None
    email.is_read = True
    _persist_email_state(email)
    return {"status": "sent", "preview": body_preview}


@router.post("/emails/{email_id}/star")
async def toggle_star(email_id: str) -> dict[str, Any]:
    """Toggle the starred state of an email."""
    email = _get_email(email_id)
    email.is_starred = not email.is_starred
    _persist_email_state(email)
    return {"id": email.id, "is_starred": email.is_starred}


@router.post("/emails/{email_id}/read")
async def mark_as_read(email_id: str) -> dict[str, Any]:
    """Mark an email as read."""
    email = _get_email(email_id)
    email.is_read = True
    _persist_email_state(email)
    return {"id": email.id, "is_read": email.is_read}


@router.post("/emails/classify-all")
async def classify_all(
    account_id: str | None = Query(None, description="Classify only one account"),
) -> list[dict[str, Any]]:
    """Batch-classify all emails that have not been classified yet."""
    _ensure_loaded()
    results = []
    for email in _emails.values():
        if account_id and email.account_id != account_id:
            continue
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
    if results:
        _log_activity("batch_classified", f"Batch classified {len(results)} emails")
    return results


@router.post("/emails/refresh")
async def refresh_emails() -> dict[str, Any]:
    """Clear the in-memory email store and re-fetch from the source.

    Useful when using IMAP to pull new mail without restarting the server.
    """
    _emails.clear()
    _ensure_loaded()
    _log_activity("refreshed", f"Inbox refreshed — {len(_emails)} emails loaded")
    return {"status": "refreshed", "count": len(_emails)}


# ---- Dashboard Endpoints ---------------------------------------------------


@router.get("/dashboard")
async def get_dashboard() -> dict[str, Any]:
    """Return aggregated dashboard statistics and AI-generated notifications."""
    _ensure_loaded()
    _generate_notifications()

    emails = list(_emails.values())
    total = len(emails)
    unread = sum(1 for e in emails if not e.is_read)
    classified = sum(1 for e in emails if e.classification)
    starred = sum(1 for e in emails if e.is_starred)

    priority_breakdown: dict[str, int] = {}
    category_breakdown: dict[str, int] = {}
    for e in emails:
        if e.classification:
            p = e.classification.priority.value
            c = e.classification.category.value
            priority_breakdown[p] = priority_breakdown.get(p, 0) + 1
            category_breakdown[c] = category_breakdown.get(c, 0) + 1

    cfg = get_settings()
    accounts = list_accounts_summary(load_accounts(cfg.data_dir))
    for account in accounts:
        account_emails = [e for e in emails if e.account_id == account["id"]]
        account["email_count"] = len(account_emails)
        account["unread_count"] = sum(1 for e in account_emails if not e.is_read)
    now = datetime.now(timezone.utc)
    upcoming = get_upcoming_events(_calendar, now, window_days=7)

    stats = DashboardStats(
        total_emails=total,
        unread_count=unread,
        classified_count=classified,
        starred_count=starred,
        priority_breakdown=priority_breakdown,
        category_breakdown=category_breakdown,
        accounts=accounts,
        upcoming_events=[ev.model_dump(mode="json") for ev in upcoming[:6]],
        notifications=[n.model_dump(mode="json") for n in _notifications],
        recent_activity=_activity_log[:8],
        storage_stats=storage_stats(),
    )
    return stats.model_dump(mode="json")


@router.get("/notifications")
async def get_notifications() -> list[dict[str, Any]]:
    """Return current AI-generated notifications."""
    _ensure_loaded()
    _generate_notifications()
    return [n.model_dump(mode="json") for n in _notifications]


@router.post("/notifications/{notif_id}/dismiss")
async def dismiss_notification(notif_id: str) -> dict[str, str]:
    """Dismiss a notification."""
    for i, n in enumerate(_notifications):
        if n.id == notif_id:
            _notifications.pop(i)
            return {"status": "dismissed"}
    raise HTTPException(status_code=404, detail="Notification not found")


# ---- Account Endpoints -----------------------------------------------------


@router.get("/accounts")
async def list_accounts() -> list[dict[str, Any]]:
    """Return configured email accounts (no credentials)."""
    cfg = get_settings()
    return list_accounts_summary(load_accounts(cfg.data_dir))


class AccountCreate(BaseModel):
    name: str
    email: str
    provider: str = "imap"
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_pass: str = ""
    imap_mailbox: str = "INBOX"
    imap_use_ssl: bool = True
    color: str = "#3b82f6"
    is_active: bool = True


class AccountUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    provider: str | None = None
    imap_host: str | None = None
    imap_port: int | None = None
    imap_user: str | None = None
    imap_pass: str | None = None
    imap_mailbox: str | None = None
    imap_use_ssl: bool | None = None
    color: str | None = None
    is_active: bool | None = None


@router.post("/accounts")
async def create_account(body: AccountCreate) -> dict[str, Any]:
    cfg = get_settings()
    accounts = load_accounts(cfg.data_dir)
    account = AccountConfig(
        id=_new_account_id(accounts, body.email),
        **body.model_dump(),
    )
    accounts.append(account)
    save_accounts(cfg.data_dir, accounts)
    _emails.clear()
    _log_activity("account_created", f"Account '{account.name}' added", account.id)
    return list_accounts_summary([account])[0]


@router.put("/accounts/{account_id}")
async def update_account(account_id: str, body: AccountUpdate) -> dict[str, Any]:
    cfg = get_settings()
    accounts = load_accounts(cfg.data_dir)
    account = get_account(accounts, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates.get("imap_pass") == "":
        updates.pop("imap_pass")
    updated = account.model_copy(update=updates)
    accounts = [updated if a.id == account_id else a for a in accounts]
    save_accounts(cfg.data_dir, accounts)
    _emails.clear()
    _log_activity("account_updated", f"Account '{updated.name}' updated", updated.id)
    return list_accounts_summary([updated])[0]


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str) -> dict[str, str]:
    cfg = get_settings()
    accounts = load_accounts(cfg.data_dir)
    if get_account(accounts, account_id) is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    remaining = [account for account in accounts if account.id != account_id]
    save_accounts(cfg.data_dir, remaining)
    _emails.clear()
    _log_activity("account_deleted", f"Account '{account_id}' removed", account_id)
    return {"status": "deleted", "account_id": account_id}


def _new_account_id(accounts: list[AccountConfig], email: str) -> str:
    base = canonicalize_inbox(email, fallback="account").split("@")[0] or "account"
    candidate = "".join(ch if ch.isalnum() else "-" for ch in base.lower()).strip("-")[:24] or "account"
    existing = {account.id for account in accounts}
    if candidate not in existing:
        return candidate
    suffix = 2
    while f"{candidate}-{suffix}" in existing:
        suffix += 1
    return f"{candidate}-{suffix}"


# ---- Calendar Endpoints ----------------------------------------------------


@router.get("/calendar")
async def get_calendar() -> list[dict[str, Any]]:
    """Return all calendar events."""
    _ensure_loaded()
    return [ev.model_dump(mode="json") for ev in _calendar]


@router.get("/calendar/upcoming")
async def get_upcoming_calendar(
    days: int = Query(7, ge=1, le=90),
) -> list[dict[str, Any]]:
    """Return upcoming calendar events within a time window."""
    _ensure_loaded()
    now = datetime.now(timezone.utc)
    upcoming = get_upcoming_events(_calendar, now, window_days=days)
    return [ev.model_dump(mode="json") for ev in upcoming]


class CalendarEventCreate(BaseModel):
    title: str
    start: str
    end: str
    description: str = ""
    location: str = ""
    color: str = "#3b82f6"
    attendees: list[str] = []
    is_all_day: bool = False


@router.post("/calendar/events")
async def create_calendar_event(body: CalendarEventCreate) -> dict[str, Any]:
    """Create a new local calendar event."""
    _ensure_loaded()
    event = create_event(_calendar, body.model_dump())
    safe_store_calendar_event(event, source="user")
    _log_activity("event_created", f"Calendar event '{event.title}' created", event.id)
    return event.model_dump(mode="json")


class CalendarEventUpdate(BaseModel):
    title: str | None = None
    start: str | None = None
    end: str | None = None
    description: str | None = None
    location: str | None = None
    color: str | None = None
    attendees: list[str] | None = None
    is_all_day: bool | None = None


@router.put("/calendar/events/{event_id}")
async def update_calendar_event(
    event_id: str,
    body: CalendarEventUpdate,
) -> dict[str, Any]:
    """Update an existing calendar event."""
    _ensure_loaded()
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = update_event(_calendar, event_id, data)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    safe_store_calendar_event(updated, source="user")
    return updated.model_dump(mode="json")


@router.delete("/calendar/events/{event_id}")
async def delete_calendar_event(event_id: str) -> dict[str, str]:
    """Delete a calendar event."""
    _ensure_loaded()
    if not delete_event(_calendar, event_id):
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    return {"status": "deleted", "event_id": event_id}


# ---- AI Endpoints (stub for orchestration phase) ---------------------------


class AskAIRequest(BaseModel):
    question: str
    context_type: str | None = None  # "email", "thread", "general"
    context_id: str | None = None    # email_id or thread_id


@router.post("/ai/ask")
async def ask_ai(body: AskAIRequest) -> dict[str, Any]:
    """Ask the AI a question about an email, thread, or general topic.

    This is a stub endpoint — full orchestration is wired in the next phase.
    """
    return {
        "answer": (
            "AI orchestration will be wired in the next phase. "
            "This endpoint will support contextual Q&A about emails, threads, "
            "calendar events, and general productivity queries."
        ),
        "context_type": body.context_type,
        "context_id": body.context_id,
        "status": "stub",
    }


# ---- Storage Endpoints -----------------------------------------------------


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
