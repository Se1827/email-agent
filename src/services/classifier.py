"""Email classification service — assigns priority and category via LLM.

Uses LangChain ChatGroq with smart calendar-context filtering: only
calendar events that are semantically relevant to the email are injected
into the prompt. Relevance is determined by date matching, attendee
overlap, and keyword overlap.

Key design decisions:
  - Quoted reply chains are stripped before date extraction to avoid
    false positives from "On Saturday, 05/16/26 at 01:18 ... wrote:"
  - Bare ordinals ("19th", "20th") infer the month from the email date
  - Meeting/critical emails auto-create calendar events for availability
  - Auto-created events are skipped if a conflicting event already exists
    on the same day and overlapping time window
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta

from src.llm import client as llm
from src.llm.date_fast import resolve_fast
from src.llm.date_resolver import ResolvedDate, resolve_proposed_datetime
from src.llm.prompts import CLASSIFY_SYSTEM, CLASSIFY_USER
from src.models.email import CalendarEvent, Category, Classification, Email, Priority
from src.services.conflicts import (
    check_full_calendar_conflict,
    format_conflict_context,
    has_calendar_conflict,
    wall_clock,
)
from src.services.pii import PrivacyGateway
from src.services.rules import evaluate_rules
from src.storage import safe_store_pii_mappings
from src.config import get_settings

log = logging.getLogger(__name__)


# ── Month name maps ────────────────────────────────────────────────────────
_MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


# ── Strip quoted reply chains ──────────────────────────────────────────────

def _strip_quoted_text(body: str) -> str:
    """Remove quoted reply chains from the email body.

    Reply chains contain dates like "On Friday, May 15, 2026 at ..." that
    the date extractor would pick up as false positives. We strip everything
    after common reply markers.
    """
    separators = [
        r"^-{3,}\s*Original\s+Message\s*-{3,}",
        r"^On\s+\w+,\s+\d{1,2}/\d{1,2}/\d{2,4}\s+at\s+",
        r"^On\s+\w+,\s+\w+\s+\d{1,2},\s+\d{4}\s+at\s+",
        r"^>",
        r"^Sent from \[",
    ]
    lines = body.splitlines()
    clean_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        is_quote = False
        for sep in separators:
            if re.match(sep, stripped, re.IGNORECASE):
                is_quote = True
                break
        if is_quote:
            break
        clean_lines.append(line)
    return "\n".join(clean_lines)


# ── Date extraction from natural language ──────────────────────────────────

def _extract_dates_from_text(text: str, reference_date: datetime) -> list[datetime]:
    """Extract date references from email text."""
    text_lower = text.lower()
    found: list[datetime] = []
    ref_year = reference_date.year
    ref_month = reference_date.month

    ordinal_with_month = set()
    for m in re.finditer(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?("
        + "|".join(_MONTH_MAP.keys())
        + r")\b",
        text_lower,
    ):
        day, month_name = int(m.group(1)), _MONTH_MAP[m.group(2)]
        ordinal_with_month.add(m.group(1))
        try:
            found.append(datetime(ref_year, month_name, day))
        except ValueError:
            pass

    for m in re.finditer(
        r"\b(" + "|".join(_MONTH_MAP.keys()) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b",
        text_lower,
    ):
        month_name, day = _MONTH_MAP[m.group(1)], int(m.group(2))
        ordinal_with_month.add(m.group(2))
        try:
            found.append(datetime(ref_year, month_name, day))
        except ValueError:
            pass

    for m in re.finditer(r"\b(\d{1,2})(st|nd|rd|th)\b", text_lower):
        day_str = m.group(1)
        if day_str in ordinal_with_month:
            continue
        day = int(day_str)
        if 1 <= day <= 31:
            try:
                candidate = datetime(ref_year, ref_month, day)
                if candidate.date() < reference_date.date():
                    next_month = ref_month + 1 if ref_month < 12 else 1
                    next_year = ref_year if ref_month < 12 else ref_year + 1
                    candidate = datetime(next_year, next_month, day)
                found.append(candidate)
            except ValueError:
                pass

    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", text_lower):
        try:
            found.append(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass

    if re.search(r"\btoday\b", text_lower):
        found.append(reference_date.replace(hour=0, minute=0, second=0, microsecond=0))
    if re.search(r"\btomorrow\b", text_lower):
        found.append((reference_date + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0))
    if re.search(r"\bday after tomorrow\b", text_lower):
        found.append((reference_date + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0))

    day_names = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }
    for name, weekday in day_names.items():
        if re.search(rf"\b{name}\b", text_lower):
            days_ahead = (weekday - reference_date.weekday()) % 7 or 7
            found.append(
                (reference_date + timedelta(days=days_ahead)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            )

    return found


def _extract_time_from_text(text: str) -> tuple[int, int] | None:
    """Extract a time reference like '4pm', '4:30pm', '16:00' from text."""
    text_lower = text.lower()

    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text_lower)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        if m.group(3) == "pm" and hour != 12:
            hour += 12
        elif m.group(3) == "am" and hour == 12:
            hour = 0
        return (hour, minute)

    m = re.search(r"\b(\d{1,2}):(\d{2})\b", text_lower)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return (hour, minute)

    return None


# ── Relevance checks ──────────────────────────────────────────────────────

def _email_mentions_time_or_dates(email: Email) -> bool:
    """Check if the email body references times, dates, or meeting concepts."""
    clean_body = _strip_quoted_text(email.body)
    text = f"{email.subject} {clean_body}".lower()

    patterns = [
        r"\b(today|tomorrow|tonight|day after tomorrow)\b",
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\b(meeting|standup|sync|call|demo|review|retro|planning|deadline|meet)\b",
        r"\b\d{1,2}:\d{2}\b",
        r"\b\d{1,2}(am|pm)\b",
        r"\b(schedule|calendar|appointment|event|free|available|busy)\b",
        r"\b\d{1,2}(st|nd|rd|th)\b",
    ]
    month_pattern = r"\b(" + "|".join(_MONTH_MAP.keys()) + r")\b"
    patterns.append(month_pattern)

    return any(re.search(p, text) for p in patterns)


def _date_overlap(email: Email, event: CalendarEvent) -> bool:
    """Check if dates mentioned in the email match the event date."""
    clean_body = _strip_quoted_text(email.body)
    text = f"{email.subject} {clean_body}"
    mentioned_dates = _extract_dates_from_text(text, email.timestamp)
    if not mentioned_dates:
        return False
    event_date = event.start.date()
    return any(d.date() == event_date for d in mentioned_dates)


def _attendee_overlap(email: Email, event: CalendarEvent) -> bool:
    """Check if email sender/recipients overlap with event attendees."""
    email_people = {email.sender.lower()} | {r.lower() for r in email.recipients}
    event_people = {a.lower() for a in event.attendees}
    return bool(email_people & event_people)


def _keyword_overlap(email: Email, event: CalendarEvent) -> bool:
    """Check if meaningful keywords from the email match the event."""
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "and", "or", "but", "if",
        "then", "else", "when", "at", "by", "for", "with", "about", "from",
        "to", "in", "on", "of", "it", "its", "this", "that", "these", "those",
        "i", "me", "my", "we", "our", "you", "your", "he", "she", "they",
        "hi", "hello", "hey", "thanks", "thank", "regards", "best", "dear",
        "please", "kindly", "not", "no", "yes", "what", "how", "why", "who",
        "where", "which", "sent", "wrote", "mail", "proton", "android",
        "original", "message",
    }
    clean_body = _strip_quoted_text(email.body)
    email_text = f"{email.subject} {clean_body}".lower()
    email_words = set(re.findall(r"[a-z]{3,}", email_text)) - stop_words

    event_text = f"{event.title} {event.description}".lower()
    event_words = set(re.findall(r"[a-z]{3,}", event_text)) - stop_words

    overlap = email_words & event_words
    distinctive = {w for w in overlap if len(w) > 5}
    return len(overlap) >= 2 or len(distinctive) >= 1


def filter_relevant_events(
    email: Email,
    events: list[CalendarEvent],
) -> list[CalendarEvent]:
    """Return only calendar events that are relevant to this email."""
    if not events:
        return []

    if not _email_mentions_time_or_dates(email):
        return []

    relevant: list[CalendarEvent] = []
    seen_ids: set[str] = set()

    for event in events:
        if event.id in seen_ids:
            continue
        if _date_overlap(email, event):
            relevant.append(event)
            seen_ids.add(event.id)
        elif _attendee_overlap(email, event):
            relevant.append(event)
            seen_ids.add(event.id)
        elif _keyword_overlap(email, event):
            relevant.append(event)
            seen_ids.add(event.id)

    log.info(
        "calendar_relevance_filter",
        extra={
            "email_id": email.id,
            "total_events": len(events),
            "relevant_events": len(relevant),
            "relevant_titles": [e.title for e in relevant],
        },
    )
    return relevant



# ── Auto-event creation from meeting / action-required emails ──────────────

def extract_meeting_event(
    email: Email,
    classification: Classification,
    existing_events: list[CalendarEvent] | None = None,
    *,
    resolved_date: ResolvedDate | None = None,
) -> CalendarEvent | None:
    """Create a calendar event from a classified meeting or action-required email.

    Uses the LLM-resolved date when available, falling back to regex extraction.

    Returns None if:
    - The email is not classified as meeting or action-required
    - No date can be resolved

    For meeting emails: skips creation if a conflicting event exists.
    For action-required emails: always creates the event (no conflict check).
    """
    category = classification.category.value
    if category not in ("meeting", "action-required"):
        return None

    # ── Resolve the date ──────────────────────────────────────────────────
    if resolved_date:
        meeting_start = resolved_date.start
        meeting_end = resolved_date.end
        is_all_day = resolved_date.is_all_day
    else:
        # Fallback to regex (only if LLM resolver wasn't called)
        clean_body = _strip_quoted_text(email.body)
        text = f"{email.subject} {clean_body}"
        dates = _extract_dates_from_text(text, email.timestamp)
        if not dates:
            return None
        meeting_date = dates[0]
        time_info = _extract_time_from_text(text)
        if time_info:
            meeting_start = meeting_date.replace(hour=time_info[0], minute=time_info[1])
            meeting_end = meeting_start + timedelta(hours=1)
            is_all_day = False
        else:
            meeting_start = meeting_date
            meeting_end = meeting_date.replace(hour=23, minute=59)
            is_all_day = True

    sender_name = email.sender.split("@")[0].replace(".", " ").title()

    if category == "action-required":
        title_prefix = "Action"
        color = "#ef4444"   # red
    else:
        title_prefix = "Meeting"
        color = "#f59e0b"   # amber

    candidate = CalendarEvent(
        id=f"auto-{email.id[:12]}",
        title=f"{title_prefix}: {sender_name} — {email.subject[:40]}",
        start=meeting_start,
        end=meeting_end,
        description=f"Auto-created from email: {email.subject}\nFrom: {email.sender}",
        color=color,
        attendees=[email.sender] + email.recipients[:5],
        is_all_day=is_all_day,
    )

    # Conflict check — meetings only; action-required always goes through
    if category == "meeting" and existing_events:
        conflict = has_calendar_conflict(candidate, existing_events)
        if conflict:
            log.info(
                "auto_event_skipped_conflict",
                extra={
                    "email_id": email.id,
                    "candidate_title": candidate.title,
                    "candidate_start": meeting_start.isoformat(),
                    "conflicting_event": conflict.title,
                    "conflicting_start": conflict.start.isoformat(),
                },
            )
            return None

    return candidate


# ── Classification ─────────────────────────────────────────────────────────

async def classify(
    email: Email,
    calendar_events: list[CalendarEvent] | None = None,
    ai_mode: str = "classic",
) -> tuple[Classification, ResolvedDate | None]:
    """Classify an email by priority and category.

    In Classic mode, uses the fast regex date resolver first, falling back
    to the LLM resolver only when the fast path returns None.

    Returns a (Classification, ResolvedDate | None) tuple. The resolved date
    is extracted by an LLM sub-agent and should be forwarded to
    ``extract_meeting_event`` so it doesn't have to re-resolve.
    """
    privacy = PrivacyGateway()
    all_events = calendar_events or []
    cfg = get_settings()

    # ── Rule engine pre-pass ────────────────────────────────────────────
    # Skip LLM for obvious spam/newsletters, pre-set priority for VIP/urgent.
    rule_verdict = evaluate_rules(email, cfg.data_dir)
    if rule_verdict.skip_llm:
        result = Classification(
            priority=rule_verdict.pre_priority or Priority.LOW,
            category=rule_verdict.pre_category or Category.SPAM,
            confidence=0.95,
            reasoning=f"Rule engine: {'; '.join(rule_verdict.reasons)}",
            explanation_factors=rule_verdict.reasons,
        )
        log.info(
            "classified_by_rules",
            extra={
                "email_id": email.id,
                "priority": result.priority.value,
                "category": result.category.value,
                "reasons": rule_verdict.reasons,
            },
        )
        return result, None

    # ── Date resolution ────────────────────────────────────────────────
    clean_body = _strip_quoted_text(email.body)

    # Classic mode: try fast regex path first, fallback to LLM
    resolved = resolve_fast(email.subject, clean_body, email.timestamp)
    if resolved is None:
        resolved = await resolve_proposed_datetime(
            email.subject, clean_body, email.timestamp,
        )

    # Build calendar context using LLM-resolved date
    if resolved:
        _cs = resolved.start
        _ce = resolved.end
        _candidate_is_all_day = resolved.is_all_day
    else:
        _cs = _ce = None
        _candidate_is_all_day = False

    # ── Narrow calendar fetch ───────────────────────────────────────────
    # Pre-filter events by date range to reduce prompt token usage.
    if resolved and resolved.date:
        # If we resolved a date, only consider events within ±2 days
        target = resolved.date.date() if hasattr(resolved.date, 'date') else resolved.date
        narrowed = [
            ev for ev in all_events
            if abs((wall_clock(ev.start).date() - target).days) <= 2
        ]
    else:
        # No date resolved — only consider events in the next 7 days
        now = datetime.now()
        narrowed = [
            ev for ev in all_events
            if 0 <= (wall_clock(ev.start).date() - now.date()).days <= 7
        ]

    relevant_events = filter_relevant_events(email, narrowed)

    cal_ctx = format_conflict_context(
        relevant_events, _cs, _ce,
        all_events=all_events,
        candidate_is_all_day=_candidate_is_all_day,
    )

    user_msg = CLASSIFY_USER.format(
        sender=privacy.mask_text(email.sender).text,
        recipients=privacy.mask_text(", ".join(email.recipients)).text,
        timestamp=email.timestamp.isoformat(),
        subject=privacy.mask_text(email.subject).text,
        body=privacy.mask_text(email.body).text,
        calendar_context=privacy.mask_text(cal_ctx).text,
    )

    raw = await llm.chat(
        messages=[
            {"role": "system", "content": CLASSIFY_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,
    )

    parsed = _parse_classification(raw)

    # ── Apply rule engine overrides ────────────────────────────────────
    # If the rule engine pre-set a priority (VIP/urgent), override the LLM.
    if rule_verdict.pre_priority is not None:
        priority_order = {Priority.CRITICAL: 3, Priority.HIGH: 2, Priority.NORMAL: 1, Priority.LOW: 0}
        if priority_order.get(rule_verdict.pre_priority, 0) > priority_order.get(parsed.priority, 0):
            parsed.priority = rule_verdict.pre_priority
            parsed.explanation_factors.extend(rule_verdict.reasons)

    # ── Append deterministic availability note to reasoning ────────────
    # Only when the LLM resolver found a proposed date (avoids false
    # positives on newsletters / informational emails).
    if resolved and _cs is not None:
        conflict = check_full_calendar_conflict(
            wall_clock(_cs), wall_clock(_ce),
            _candidate_is_all_day, all_events,
        )
        if conflict:
            parsed.reasoning = (
                f"{parsed.reasoning} — "
                f"You are NOT available at the proposed time: "
                f"conflict with \"{conflict.title}\""
            )
            parsed.explanation_factors.append(f"conflict with \"{conflict.title}\"")
        else:
            parsed.reasoning = (
                f"{parsed.reasoning} — "
                f"You ARE available at the proposed time."
            )
            parsed.explanation_factors.append("available at proposed time")

    safe_store_pii_mappings(email.id, "classification", privacy.mappings)
    log.info(
        "classified",
        extra={
            "email_id": email.id,
            "priority": parsed.priority.value,
            "category": parsed.category.value,
            "relevant_events": len(relevant_events),
            "total_events": len(all_events),
            "resolved_date": resolved.date.isoformat() if resolved else None,
            "resolved_is_all_day": resolved.is_all_day if resolved else None,
            "ai_mode": ai_mode,
        },
    )
    return parsed, resolved


def _parse_classification(raw: str) -> Classification:
    """Parse the LLM's JSON output into a Classification model."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])

    data = json.loads(text)
    return Classification.model_validate(data)