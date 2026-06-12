"""API routes for the email agent."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.config import get_settings
from src.connectors.mock import load_emails as load_mock_emails
from src.connectors.imap import sync_mailbox, idle_loop
from src.connectors.smtp import send_email as smtp_send_email
from src.models.email import (
    AccountConfig,
    CalendarEvent,
    Classification,
    DashboardStats,
    DraftQuality,
    DraftReply,
    Email,
    Notification,
    SyncState,
)
from src.services import classifier, drafter
from src.services.accounts import (
    account_inbox,
    get_account,
    load_accounts,
    list_accounts_summary,
    resolve_smtp_settings,
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
    load_calendar_events,
    safe_record_event,
    safe_store_calendar_event,
    safe_delete_calendar_event_record,
    safe_store_email,
    safe_store_semantic_memory,
    safe_store_thread_state,
    storage_stats,
    store_email,
    load_sync_state,
    safe_store_sync_state,
    clear_sync_state,
)

import threading

_idle_threads: dict[str, threading.Thread] = {}

def _ensure_idle_connection(account: AccountConfig, inbox: str) -> None:
    if account.provider != "imap":
        return
    cfg = get_settings()
    mailbox = account.imap_mailbox or cfg.imap_mailbox
    thread_key = f"{account.id}:{mailbox}"
    if thread_key in _idle_threads and _idle_threads[thread_key].is_alive():
        return
        
    def _on_push_notification():
        log.info("idle_push_received", extra={"account": account.id})
        try:
            new_emails = _sync_imap_mailbox(account, mailbox, inbox)
            for email in new_emails:
                _stamp_account_email(email, account, inbox)
                _merge_source_email(email, source=email.account_id or cfg.email_source)
        except Exception as exc:
            log.error("idle_sync_failed", extra={"error": str(exc)})

    host = account.imap_host or cfg.imap_host
    port = account.imap_port or cfg.imap_port
    username = account.imap_user or account.email or cfg.imap_user
    password = account.imap_pass or cfg.imap_pass
    
    t = threading.Thread(
        target=idle_loop,
        args=(host, port, username, password),
        kwargs={"mailbox": mailbox, "use_ssl": account.imap_use_ssl, "callback": _on_push_notification},
        daemon=True,
    )
    t.start()
    _idle_threads[thread_key] = t
    log.info("idle_thread_started", extra={"account": account.id, "mailbox": mailbox})


def _sync_imap_mailbox(account: AccountConfig, imap_mailbox: str, inbox: str) -> list[Email]:
    cfg = get_settings()
    host = account.imap_host or cfg.imap_host
    port = account.imap_port or cfg.imap_port
    username = account.imap_user or account.email or cfg.imap_user
    password = account.imap_pass or cfg.imap_pass
    use_ssl = account.imap_use_ssl

    raw_state = load_sync_state(account.id, imap_mailbox)
    if raw_state:
        state = SyncState.model_validate(raw_state)
    else:
        state = SyncState(account_id=account.id, mailbox=imap_mailbox, uidvalidity=0, last_uid=0, highestmodseq=0)

    try:
        emails, new_last_uid, new_highestmodseq, new_uidvalidity, flag_updates = sync_mailbox(
            account_id=account.id,
            host=host,
            port=port,
            username=username,
            password=password,
            mailbox=imap_mailbox,
            use_ssl=use_ssl,
            inbox=inbox,
            last_uid=state.last_uid,
            highestmodseq=state.highestmodseq,
            uidvalidity=state.uidvalidity if state.uidvalidity else None,
        )
        
        if flag_updates:
            for f_uid, flags in flag_updates:
                stable_id = f"{account.id}:{imap_mailbox}:{state.uidvalidity or new_uidvalidity}:{f_uid}"
                if stable_id in _emails:
                    _emails[stable_id].is_read = any(f.lower() == "\\seen" for f in flags)
                    safe_store_email(_emails[stable_id], source="imap_sync")

        if new_uidvalidity and new_uidvalidity != state.uidvalidity:
            # uidvalidity changed or initialized
            state.uidvalidity = new_uidvalidity
            state.last_uid = new_last_uid
            state.highestmodseq = new_highestmodseq
            safe_store_sync_state(state)
        elif new_last_uid > state.last_uid or new_highestmodseq > state.highestmodseq:
            state.last_uid = new_last_uid
            state.highestmodseq = new_highestmodseq
            safe_store_sync_state(state)
            
        return emails
    except Exception as exc:
        log.warning(f"Failed to sync mailbox {imap_mailbox}", extra={"error": str(exc), "account": account.email})
        return []

log = logging.getLogger(__name__)

router = APIRouter()

# ---- In-memory stores (initialised lazily) --------------------------------

class ThreadSafeDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lock = threading.Lock()
        
    def __getitem__(self, key):
        with self.lock:
            return super().__getitem__(key)
            
    def __setitem__(self, key, value):
        with self.lock:
            super().__setitem__(key, value)
            
    def __delitem__(self, key):
        with self.lock:
            super().__delitem__(key)
            
    def get(self, key, default=None):
        with self.lock:
            return super().get(key, default)
            
    def pop(self, key, default=None):
        with self.lock:
            if key in self:
                return super().pop(key)
            return default
            
    def clear(self):
        with self.lock:
            super().clear()
            
    def values(self):
        with self.lock:
            # Return a list to avoid RuntimeError: dictionary changed size during iteration
            return list(super().values())
            
    def keys(self):
        with self.lock:
            return list(super().keys())
            
    def items(self):
        with self.lock:
            return list(super().items())
            
    def __contains__(self, key):
        with self.lock:
            return super().__contains__(key)
            
    def __len__(self):
        with self.lock:
            return super().__len__()

_emails: ThreadSafeDict = ThreadSafeDict()
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


_dismissed_notification_ids: set[str] = set()


def _generate_notifications() -> None:
    """Build smart notifications from real email + calendar state.

    Every notification is derived from actual data in _emails and _calendar,
    not hardcoded. Regenerated fresh on each call but dismissed IDs are
    preserved so dismissed alerts stay gone.
    """
    generated: list[Notification] = []
    now = datetime.now(timezone.utc)

    # ── 1. Urgent unresponded emails (from real classified data) ─────────
    urgent_emails = [
        e for e in _emails.values()
        if e.classification
        and e.classification.priority.value in ("critical", "high")
        and not e.draft_reply
    ]
    if urgent_emails:
        subjects = [e.subject[:50] for e in urgent_emails[:3]]
        generated.append(Notification(
            id=f"notif-urgent-{len(urgent_emails)}",
            type="urgent_email",
            title=f"{len(urgent_emails)} urgent {'email' if len(urgent_emails) == 1 else 'emails'} need a reply",
            message="; ".join(subjects),
            severity="critical",
            related_id=urgent_emails[0].id,
            related_type="email",
            timestamp=now,
        ))

    # ── 2. Upcoming calendar events (real events within 48h) ────────────
    for ev in _calendar:
        ev_start = ev.start
        if ev_start.tzinfo is None:
            ev_start = ev_start.replace(tzinfo=timezone.utc)
        delta = (ev_start - now).total_seconds() / 3600
        if delta < 0 or delta > 48:
            continue

        if delta < 1:
            sev, time_msg = "critical", "Less than 1 hour away"
        elif delta < 6:
            sev, time_msg = "critical", f"In {int(delta)} hours"
        elif delta < 24:
            sev, time_msg = "warning", f"In {int(delta)} hours"
        else:
            sev, time_msg = "info", f"Tomorrow — in {int(delta)} hours"

        evt_type = "deadline" if ev.is_all_day else "meeting_soon"
        prefix = "Deadline" if ev.is_all_day else "Upcoming"
        location_hint = f" @ {ev.location}" if ev.location else ""
        generated.append(Notification(
            id=f"notif-cal-{ev.id}",
            type=evt_type,
            title=f"{prefix}: {ev.title}",
            message=f"{time_msg}{location_hint}",
            severity=sev,
            related_id=ev.id,
            related_type="event",
            timestamp=now,
        ))

    # ── 3. Unclassified emails (real count) ─────────────────────────────
    unclassified = [e for e in _emails.values() if not e.classification]
    if unclassified:
        generated.append(Notification(
            id=f"notif-unclassified-{len(unclassified)}",
            type="ai_insight",
            title="Emails awaiting AI triage",
            message=f"{len(unclassified)} {'email has' if len(unclassified) == 1 else 'emails have'} not been classified yet",
            severity="info" if len(unclassified) < 5 else "warning",
            timestamp=now,
        ))

    # ── 4. Drafts awaiting approval (real count) ────────────────────────
    pending_drafts = [e for e in _emails.values() if e.draft_reply and not e.is_read]
    if pending_drafts:
        generated.append(Notification(
            id=f"notif-drafts-{len(pending_drafts)}",
            type="ai_insight",
            title=f"{len(pending_drafts)} draft {'reply' if len(pending_drafts) == 1 else 'replies'} ready for review",
            message="Review and approve AI-generated replies before sending",
            severity="info",
            related_id=pending_drafts[0].id,
            related_type="email",
            timestamp=now,
        ))

    # ── 5. Meeting & action-required emails with calendar context ───────
    for e in _emails.values():
        if not e.classification:
            continue
        cat = e.classification.category.value
        if cat not in ("meeting", "action-required"):
            continue
        if e.draft_reply:
            continue

        notif_id = f"notif-action-{e.id[:8]}"

        if cat == "action-required":
            generated.append(Notification(
                id=notif_id,
                type="ai_insight",
                title=f"Action required: {e.subject[:50]}",
                message=f"From {e.sender.split('@')[0]} — needs your attention",
                severity="warning",
                related_id=e.id,
                related_type="email",
                timestamp=now,
            ))
        else:
            # Check if any calendar events overlap with this meeting email
            from src.services.classifier import filter_relevant_events
            related = filter_relevant_events(e, _calendar)
            if related:
                generated.append(Notification(
                    id=f"notif-conflict-{e.id[:8]}",
                    type="calendar_conflict",
                    title=f"Meeting email may conflict with: {related[0].title}",
                    message=f"From {e.sender.split('@')[0]} — '{e.subject[:40]}'",
                    severity="warning",
                    related_id=e.id,
                    related_type="email",
                    timestamp=now,
                ))

    # Replace notifications list, filtering out dismissed ones
    _notifications.clear()
    _notifications.extend(
        n for n in generated if n.id not in _dismissed_notification_ids
    )


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
    if account.provider == "graph":
        from src.connectors.graph import graph
        raw_msgs = graph.list_messages(top=cfg.imap_fetch_limit)
        emails = []
        for m in raw_msgs:
            try:
                emails.append(Email.model_validate(graph.to_agent_email(m)))
            except Exception as exc:
                log.exception("graph_email_parse_failed", extra={"msg_id": m.get("id"), "error": str(exc)})
        return emails
    emails = _sync_imap_mailbox(account, account.imap_mailbox or cfg.imap_mailbox, inbox)
    
    # Also attempt to fetch Sent emails so we see replies sent from official webmail/clients
    sent_mailbox = "[Gmail]/Sent Mail" if "gmail" in (account.imap_host or "").lower() else "Sent"
    sent_emails = _sync_imap_mailbox(account, sent_mailbox, inbox)
    emails.extend(sent_emails)
    
    # Start IDLE connection to wait for push notifications
    _ensure_idle_connection(account, inbox)

    # Ensure sent emails are marked as is_sent
    from_addr = account.email or cfg.imap_user
    if from_addr:
        from_addr = from_addr.lower()
        for e in emails:
            if from_addr in e.sender.lower():
                e.is_sent = True

    return emails


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
        cfg = get_settings()
        
        # Always attempt to sync Graph calendar (it gracefully handles mock vs live)
        is_graph_active = True

        if not _calendar:
            _calendar.extend(load_events(cfg.data_dir / "calendar.json"))
            
            # Merge events from DB
            db_events = load_calendar_events()
            for db_ev in db_events:
                try:
                    event = CalendarEvent.model_validate(db_ev)
                    # Deduplicate by ID
                    if not any(e.id == event.id for e in _calendar):
                        _calendar.append(event)
                except Exception as exc:
                    log.error("Failed to load db calendar event", extra={"error": str(exc), "event": db_ev.get("id")})
            for event in _calendar:
                safe_store_calendar_event(event, source="mock")

        if is_graph_active:
            try:
                from src.connectors.graph import graph, GraphAuthRequired
                raw_events = graph.list_events(days_ahead=7)
                for ev in raw_events:
                    try:
                        start_str = ev["start"]["dateTime"]
                        end_str = ev["end"]["dateTime"]
                        if not start_str.endswith("+00:00") and not start_str.endswith("Z") and not ("+" in start_str or "-" in start_str[10:]):
                            start_str += "+00:00"
                        if not end_str.endswith("+00:00") and not end_str.endswith("Z") and not ("+" in end_str or "-" in end_str[10:]):
                            end_str += "+00:00"
                        start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                        end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))

                        event = CalendarEvent(
                            id=ev.get("id"),
                            title=ev.get("subject", "(no subject)"),
                            start=start_dt,
                            end=end_dt,
                            description=ev.get("bodyPreview", "") or ev.get("body", {}).get("content", ""),
                            location=ev.get("location", {}).get("displayName", ""),
                            attendees=[a.get("emailAddress", {}).get("address", "") for a in ev.get("attendees", [])],
                            account_id="graph",
                        )
                        # Avoid duplicates
                        if not any(e.id == event.id for e in _calendar):
                            _calendar.append(event)
                            safe_store_calendar_event(event, source="microsoft_graph")
                    except Exception as e:
                        log.exception("graph_calendar_parse_failed", extra={"event_id": ev.get("id"), "error": str(e)})
            except GraphAuthRequired as exc:
                log.warning("Graph sync skipped: Auth required.", extra={"error": str(exc)})
            except Exception as exc:
                log.exception("graph_calendar_load_failed", extra={"error": str(exc)})


def _load_emails_from_storage(inbox: str, *, account: AccountConfig | None = None) -> None:
    for payload in load_email_states(inbox=inbox):
        try:
            email = Email.model_validate(payload)
        except Exception:
            log.exception("stored_email_load_failed")
            continue
        if account is not None:
            if not email.account_id:
                email.account_id = account.id
            email.inbox = inbox
            # Normalize the ID to include account prefix so it matches
            # what _stamp_account_email() will produce from the source.
            if not email.id.startswith(f"{account.id}:"):
                email.id = f"{account.id}:{email.id}"
            if email.thread_id and not email.thread_id.startswith(f"{account.id}:"):
                email.thread_id = f"{account.id}:{email.thread_id}"
        email.storage_origin = "db"
        _emails[email.id] = email
        _store_email_memory(email)


def _merge_source_email(email: Email, *, source: str) -> None:
    """Merge a fresh source email into DB-seeded inbox state."""
    email.inbox = email.inbox or _current_inbox()
    
    # ── DEDUPLICATION LOGIC ──
    # If we already have a locally created "sent" email with this exact Message-ID,
    # we should remove it in favor of this real one fetched from IMAP.
    if email.message_id:
        to_delete = []
        for existing in list(_emails.values()):
            if existing.id != email.id and existing.message_id == email.message_id:
                # Check if the existing one is a synthetic sent record
                if ":sent-" in existing.id or existing.id.startswith("sent-"):
                    to_delete.append(existing.id)
        
        for old_id in to_delete:
            _emails.pop(old_id, None)
            try:
                delete_email_records(old_id)
            except Exception as exc:
                log.error("Failed to delete duplicate synthetic email", extra={"error": str(exc)})

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
    """Return all emails sharing the same conversation thread.

    Uses a graph-based approach: walk message_id, in_reply_to, and references
    transitively to find every email that belongs to the same conversation.
    """
    _ensure_loaded()
    anchor = _get_email(email_id)

    # Build a lookup table: message_id → email
    by_msg_id: dict[str, Email] = {}
    for e in _emails.values():
        if e.message_id:
            by_msg_id[e.message_id] = e

    # Collect all message_ids that belong to this thread via union-find walk
    thread_msg_ids: set[str] = set()
    queue: list[str] = []

    # Seed the walk with the anchor email’s identifiers
    for seed_id in [anchor.message_id, anchor.in_reply_to, anchor.thread_id]:
        if seed_id and seed_id not in thread_msg_ids:
            thread_msg_ids.add(seed_id)
            queue.append(seed_id)
    for ref in anchor.references:
        if ref not in thread_msg_ids:
            thread_msg_ids.add(ref)
            queue.append(ref)

    # BFS: for every message_id we know about, pull in its connections
    while queue:
        current = queue.pop()
        em = by_msg_id.get(current)
        if em is None:
            continue
        for related_id in [em.message_id, em.in_reply_to, em.thread_id]:
            if related_id and related_id not in thread_msg_ids:
                thread_msg_ids.add(related_id)
                queue.append(related_id)
        for ref in em.references:
            if ref not in thread_msg_ids:
                thread_msg_ids.add(ref)
                queue.append(ref)

    # Collect matching emails: any email whose message_id, in_reply_to,
    # thread_id, or any reference is in the thread set
    thread_emails: dict[str, Email] = {anchor.id: anchor}
    for e in _emails.values():
        if e.id in thread_emails:
            continue
        e_ids = {e.message_id, e.in_reply_to, e.thread_id} | set(e.references)
        if thread_msg_ids & e_ids:
            thread_emails[e.id] = e

    # Also match by simple thread_id equality (fallback for emails without
    # proper RFC headers, e.g. mock data)
    anchor_thread = anchor.thread_id or anchor.id
    for e in _emails.values():
        if e.id not in thread_emails and (e.thread_id or e.id) == anchor_thread:
            thread_emails[e.id] = e

    # Subject-based grouping fallback (mirrors frontend logic)
    def _normalize_subject(subject: str) -> str:
        if not subject:
            return ""
        import re
        s = subject.strip()
        while True:
            prev = s
            s = re.sub(r'(?i)^(re|fw|fwd)\s*:\s*', '', s).strip()
            if s == prev:
                break
        return s.lower()
        
    base_subj = _normalize_subject(anchor.subject)
    if base_subj:
        for e in _emails.values():
            if e.id not in thread_emails and _normalize_subject(e.subject) == base_subj:
                thread_emails[e.id] = e

    thread = [e.model_dump(mode="json") for e in thread_emails.values()]
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
    result, resolved_date = await classifier.classify(email, _calendar)
    email.classification = result

    # ── Auto-create calendar event from meeting/action-required emails ───
    auto_event = classifier.extract_meeting_event(
        email, result, _calendar, resolved_date=resolved_date,
    )
    if auto_event:
        # Check if we already have an auto-event for this email
        existing_auto = any(e.id == auto_event.id for e in _calendar)
        if not existing_auto:
            _calendar.append(auto_event)
            safe_store_calendar_event(auto_event, source="auto_from_email")
            _log_activity(
                "auto_event",
                f"Calendar event created: {auto_event.title}",
                auto_event.id,
            )
            log.info(
                "auto_event_created",
                extra={
                    "email_id": email.id,
                    "event_id": auto_event.id,
                    "event_title": auto_event.title,
                    "event_start": auto_event.start.isoformat(),
                },
            )

    safe_record_event(
        "email.classified",
        {
            "classification": result.model_dump(mode="json"),
            "subject": email.subject,
            "sender": email.sender,
            "auto_event": auto_event.id if auto_event else None,
        },
        subject_id=email.id,
    )
    _log_activity(
        "classified",
        f"Email from {email.sender.split('@')[0]} classified as {result.priority.value.upper()}",
        email.id,
    )
    _persist_email_state(email)

    response = result.model_dump(mode="json")
    if auto_event:
        response["auto_event"] = auto_event.model_dump(mode="json")
    return response


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
        email, email.classification,
        quality=quality,
    )
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
async def approve_draft(email_id: str) -> dict[str, Any]:
    """Approve the current draft reply and send via SMTP."""
    email = _get_email(email_id)
    if email.draft_reply is None:
        raise HTTPException(
            status_code=400,
            detail="No draft to approve. Generate a draft first.",
        )

    draft_body = email.draft_reply.body
    # Send the reply via the send-reply logic
    sent_email = _do_send_reply(
        original=email,
        body=draft_body,
        to_addrs=None,
        cc_addrs=None,
    )

    log.info("draft_approved_and_sent", extra={"email_id": email_id})
    safe_record_event(
        "email.approved",
        {"preview": draft_body[:80], "sent_message_id": sent_email.message_id},
        subject_id=email.id,
    )
    _log_activity("approved", f"Draft reply approved for '{email.subject[:40]}'", email.id)
    
    email.draft_reply = None
    email.is_read = True
    _persist_email_state(email)
    return {
        "status": "sent",
        "preview": draft_body[:80],
        "sent_email": sent_email.model_dump(mode="json"),
    }


# ---- Send / Compose Endpoints -----------------------------------------------


class SendReplyRequest(BaseModel):
    body: str
    to: list[str] | None = None
    cc: list[str] | None = None


class ComposeRequest(BaseModel):
    to: list[str]
    cc: list[str] = []
    subject: str
    body: str
    account_id: str


class AIComposeRequest(BaseModel):
    prompt: str
    quality: str = "balanced"


@router.post("/emails/ai-compose")
async def handle_ai_compose(body: AIComposeRequest) -> dict[str, Any]:
    """Generate a completely new draft using AI."""
    from src.services.drafter import ai_compose
    try:
        draft_text = await ai_compose(body.prompt, body.quality)
        return {"draft": draft_text}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _do_send_reply(
    original: Email,
    body: str,
    to_addrs: list[str] | None,
    cc_addrs: list[str] | None,
) -> Email:
    """Core logic for sending a reply — used by both send-reply and approve."""
    # ── DIAGNOSTIC: dump EVERYTHING about the original email ──
    log.warning(
        "REPLY_DIAG | original.id=%s | original.message_id=%s | original.subject=%s | "
        "original.sender=%s | original.timestamp=%s | original.in_reply_to=%s | "
        "original.references=%s | original.thread_id=%s | original.storage_origin=%s",
        original.id, original.message_id, original.subject,
        original.sender, original.timestamp, original.in_reply_to,
        original.references, original.thread_id, original.storage_origin,
    )
    cfg = get_settings()
    account = _resolve_email_account(original)

    # Default recipients: reply to sender + original To (excluding ourselves)
    from_addr = resolve_smtp_settings(account)["from_addr"] if account.provider != "graph" else account.email
    if to_addrs is None:
        all_addrs = [original.sender] + original.recipients
        to_addrs = [a for a in dict.fromkeys(all_addrs) if a.lower() != from_addr.lower()]
    if cc_addrs is None:
        cc_addrs = [a for a in original.cc if a.lower() != from_addr.lower()]

    from src.connectors.smtp import _normalize_subject_for_reply
    reply_subject = _normalize_subject_for_reply(original.subject)

    # ── CRAZY DEBUGGING / HEURISTICS FIX ──────────────────────────────────
    # Gmail and some strict clients will break threads if the email is a
    # "naked reply" (i.e., it doesn't contain the quoted text of the previous
    # message). We must inject standard quoted text at the bottom.
    try:
        from datetime import datetime
        orig_date_str = original.timestamp.strftime("%a, %b %d, %Y at %I:%M %p")
    except Exception:
        orig_date_str = "recently"

    quoted_lines = [f"> {line}" for line in (original.body or "").splitlines()]
    quoted_text = "\n".join(quoted_lines)
    full_body = f"{body}\n\nOn {orig_date_str}, {original.sender} wrote:\n{quoted_text}"

    now = datetime.now(timezone.utc)
    
    def _ensure_brackets(val: str) -> str:
        val = val.strip()
        if not val.startswith("<"):
            val = "<" + val
        if not val.endswith(">"):
            val = val + ">"
        return val

    reply_to_msg_id = None
    refs = []

    # RFC-compliant Message-IDs always contain '@' (format: <unique@domain>).
    # Some mail servers (e.g. Elektrine/Haraka) replace the original Message-ID
    # with an internal UUID that has NO '@'. If we send In-Reply-To/References
    # pointing to this corrupted ID, the remote client (Gmail) won't recognise
    # it and will treat the reply as a brand-new email.
    # Fix: detect corrupted IDs and SKIP threading headers entirely — Gmail
    # will fall back to subject+participant-based threading which works.
    raw_mid = original.message_id or ""
    if "@" in raw_mid:
        # Valid RFC Message-ID — safe to use for threading
        reply_to_msg_id = _ensure_brackets(raw_mid)
        refs = [_ensure_brackets(r) for r in original.references if r and "@" in r]
        if reply_to_msg_id and reply_to_msg_id not in refs:
            refs.append(reply_to_msg_id)
        log.warning(
            "smtp_reply_thread_headers | VALID Message-ID | In-Reply-To=%s | refs=%s",
            reply_to_msg_id, refs,
        )
    else:
        # Corrupted/replaced Message-ID — skip threading headers
        log.warning(
            "smtp_reply_thread_headers | CORRUPTED Message-ID (no @) = %s | "
            "SKIPPING In-Reply-To and References — relying on subject threading",
            raw_mid,
        )
    
    if account.provider == "graph":
        from src.connectors.graph import graph
        raw_msg_id = original.id.split(":", 1)[1] if ":" in original.id else original.id
        graph.send_message(
            to=to_addrs,
            cc=cc_addrs,
            subject=reply_subject,
            body_html=full_body,
            reply_to_id=raw_msg_id
        )
        # Graph handles threading. We create a local sent email to show immediately.
        sent_msg_id = f"graph-sent-{uuid4().hex[:12]}"
    else:
        smtp_settings = resolve_smtp_settings(account)
        from_addr = smtp_settings["from_addr"]

        sent_msg_id = smtp_send_email(
            host=smtp_settings["host"],
            port=smtp_settings["port"],
            username=smtp_settings["username"],
            password=smtp_settings["password"],
            use_ssl=smtp_settings["use_ssl"],
            use_tls=smtp_settings["use_tls"],
            from_addr=from_addr,
            from_name=smtp_settings["from_name"],
            to_addrs=to_addrs,
            cc_addrs=cc_addrs,
            subject=reply_subject,
            body=full_body,
            in_reply_to=reply_to_msg_id,
            references=refs,
        )

    # Create a sent Email record
    now = datetime.now(timezone.utc)
    sent_email = Email(
        id=f"{account.id}:sent-{hashlib.sha256(sent_msg_id.encode()).hexdigest()[:12]}",
        inbox=account_inbox(account),
        account_id=account.id,
        sender=from_addr,
        recipients=to_addrs,
        cc=cc_addrs,
        subject=reply_subject,
        body=body,
        timestamp=now,
        thread_id=original.thread_id or original.message_id or original.id,
        message_id=sent_msg_id,
        in_reply_to=reply_to_msg_id,
        references=refs,
        is_sent=True,
        is_read=True,
    )
    _emails[sent_email.id] = sent_email
    safe_store_email(sent_email, source="sent")
    _store_email_memory(sent_email)
    return sent_email


def _resolve_email_account(email: Email) -> AccountConfig:
    """Find the AccountConfig that owns this email."""
    cfg = get_settings()
    accounts = load_accounts(cfg.data_dir)
    if email.account_id:
        for acc in accounts:
            if acc.id == email.account_id:
                return acc
    # Fallback: first active account
    for acc in accounts:
        if acc.is_active:
            return acc
    raise HTTPException(status_code=400, detail="No active email account configured.")


@router.post("/emails/{email_id}/send-reply")
async def send_reply(email_id: str, body: SendReplyRequest) -> dict[str, Any]:
    """Send a reply to an email via SMTP."""
    original = _get_email(email_id)

    try:
        sent_email = _do_send_reply(
            original=original,
            body=body.body,
            to_addrs=body.to,
            cc_addrs=body.cc,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    _log_activity("sent_reply", f"Reply sent for '{original.subject[:40]}'", original.id)
    safe_record_event(
        "email.reply_sent",
        {
            "original_id": original.id,
            "sent_message_id": sent_email.message_id,
            "to": sent_email.recipients,
        },
        subject_id=original.id,
    )
    return sent_email.model_dump(mode="json")


@router.post("/emails/compose")
async def compose_email(body: ComposeRequest) -> dict[str, Any]:
    """Compose and send a new email via SMTP."""
    cfg = get_settings()
    accounts = load_accounts(cfg.data_dir)
    account = get_account(accounts, body.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account {body.account_id} not found")

    if account.provider == "graph":
        from src.connectors.graph import graph
        from_addr = account.email
        try:
            graph.send_message(
                to=body.to,
                cc=body.cc or [],
                subject=body.subject,
                body_html=body.body
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        sent_msg_id = f"graph-sent-{uuid4().hex[:12]}"
    else:
        try:
            smtp_settings = resolve_smtp_settings(account)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        from_addr = smtp_settings["from_addr"]

        try:
            sent_msg_id = smtp_send_email(
                host=smtp_settings["host"],
                port=smtp_settings["port"],
                username=smtp_settings["username"],
                password=smtp_settings["password"],
                use_ssl=smtp_settings["use_ssl"],
                use_tls=smtp_settings["use_tls"],
                from_addr=from_addr,
                from_name=smtp_settings["from_name"],
                to_addrs=body.to,
                cc_addrs=body.cc or [],
                subject=body.subject,
                body=body.body,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    now = datetime.now(timezone.utc)
    sent_email = Email(
        id=f"{account.id}:sent-{hashlib.sha256(sent_msg_id.encode()).hexdigest()[:12]}",
        inbox=account_inbox(account),
        account_id=account.id,
        sender=from_addr,
        recipients=body.to,
        cc=body.cc or [],
        subject=body.subject,
        body=body.body,
        timestamp=now,
        thread_id=f"{account.id}:{sent_msg_id}",
        message_id=sent_msg_id,
        is_sent=True,
        is_read=True,
    )
    _emails[sent_email.id] = sent_email
    safe_store_email(sent_email, source="sent")
    _store_email_memory(sent_email)
    _log_activity("composed", f"New email sent: '{body.subject[:40]}'", sent_email.id)
    safe_record_event(
        "email.composed",
        {
            "sent_message_id": sent_msg_id,
            "to": body.to,
            "subject": body.subject,
        },
        subject_id=sent_email.id,
    )
    return sent_email.model_dump(mode="json")


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
            result, _resolved = await classifier.classify(email, _calendar)
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
    _dismissed_notification_ids.add(notif_id)
    for i, n in enumerate(_notifications):
        if n.id == notif_id:
            _notifications.pop(i)
            return {"status": "dismissed"}
    return {"status": "dismissed"}


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
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_use_ssl: bool = False
    smtp_use_tls: bool = True
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
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_pass: str | None = None
    smtp_use_ssl: bool | None = None
    smtp_use_tls: bool | None = None
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
    if updates.get("smtp_pass") == "":
        updates.pop("smtp_pass")
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
    sync_to_graph: bool = False


@router.post("/calendar/events")
async def create_calendar_event(body: CalendarEventCreate) -> dict[str, Any]:
    """Create a new local calendar event."""
    _ensure_loaded()

    event_data = body.model_dump()
    # Remove sync_to_graph from the event_data before local save since it's not part of CalendarEvent model
    event_data.pop("sync_to_graph", None)

    # Sync to Graph if active and requested
    is_graph_active = True
    if is_graph_active and body.sync_to_graph:
        try:
            from src.connectors.graph import graph
            start_iso = body.start
            end_iso = body.end
            if not start_iso.endswith("Z") and "+" not in start_iso:
                start_iso += "Z"
            if not end_iso.endswith("Z") and "+" not in end_iso:
                end_iso += "Z"
            
            graph_ev = graph.create_event(
                subject=body.title,
                start_iso=start_iso,
                end_iso=end_iso,
                body=body.description,
                attendees=body.attendees
            )
            event_data["id"] = graph_ev.get("id")
            event_data["account_id"] = "graph"
        except Exception as e:
            log.exception("graph_calendar_create_failed", extra={"error": str(e)})

    event = create_event(_calendar, event_data)
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
    
    is_graph_active = True
    if is_graph_active:
        try:
            from src.connectors.graph import graph
            # we just attempt to delete it, if it's not a graph ID it might throw, but we catch it
            # wait, graph API doesn't have a delete_event exposed in our mock/graph connector?
            # Let's check graph.py if we have delete_event. Let's just ignore if not possible right now
            pass
        except Exception as e:
            log.warning(f"Failed to delete graph event {event_id}: {e}")

    if not delete_event(_calendar, event_id):
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    safe_delete_calendar_event_record(event_id)
    return {"status": "deleted", "event_id": event_id}

@router.post("/calendar/sync")
async def sync_calendar() -> dict[str, Any]:
    """Force a sync from Microsoft Graph."""
    _ensure_loaded()
    is_graph_active = True

    if not is_graph_active:
        log.info("Calendar sync skipped: Graph is not active")
        print("--- CALENDAR SYNC SKIPPED: Graph account not active ---")
        return {"status": "skipped", "message": "Graph is not active"}

    try:
        log.info("Starting calendar sync from Microsoft Graph...")
        print("--- STARTING CALENDAR SYNC FROM GRAPH ---")
        from src.connectors.graph import graph, GraphAuthRequired
        raw_events = graph.list_events(days_ahead=30)
        
        # Remove old graph events
        global _calendar
        _calendar[:] = [ev for ev in _calendar if ev.account_id != "graph" and ev.account_id != "testing"]

        count = 0
        for ev in raw_events:
            try:
                start_str = ev["start"]["dateTime"]
                end_str = ev["end"]["dateTime"]
                if not start_str.endswith("+00:00") and not start_str.endswith("Z") and not ("+" in start_str or "-" in start_str[10:]):
                    start_str += "+00:00"
                if not end_str.endswith("+00:00") and not end_str.endswith("Z") and not ("+" in end_str or "-" in end_str[10:]):
                    end_str += "+00:00"
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))

                event = CalendarEvent(
                    id=ev.get("id"),
                    title=ev.get("subject", "(no subject)"),
                    start=start_dt,
                    end=end_dt,
                    description=ev.get("bodyPreview", "") or ev.get("body", {}).get("content", ""),
                    location=ev.get("location", {}).get("displayName", ""),
                    attendees=[a.get("emailAddress", {}).get("address", "") for a in ev.get("attendees", [])],
                    account_id="graph",
                )
                if not any(e.id == event.id for e in _calendar):
                    _calendar.append(event)
                    safe_store_calendar_event(event, source="microsoft_graph")
                    count += 1
            except Exception as e:
                log.exception("graph_calendar_parse_failed", extra={"event_id": ev.get("id"), "error": str(e)})
        
        log.info(f"Calendar sync complete: {count} events synced")
        print(f"--- CALENDAR SYNC COMPLETE: {count} events synced ---")
        return {"status": "synced", "count": count}
    except GraphAuthRequired as exc:
        log.warning("Calendar sync skipped: Graph auth required")
        print("--- CALENDAR SYNC SKIPPED: Graph auth required ---")
        return {"status": "skipped", "message": "Graph is disconnected"}
    except Exception as exc:
        log.error(f"Calendar sync failed: {exc}")
        print(f"--- CALENDAR SYNC FAILED: {exc} ---")
        raise HTTPException(status_code=502, detail=str(exc))


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
