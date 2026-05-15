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
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta

from src.llm import client as llm
from src.llm.prompts import CLASSIFY_SYSTEM, CLASSIFY_USER
from src.models.email import CalendarEvent, Classification, Email
from src.services.pii import PrivacyGateway
from src.storage import safe_store_pii_mappings

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
    # Split on common reply separators
    separators = [
        r"^-{3,}\s*Original\s+Message\s*-{3,}",  # -------- Original Message --------
        r"^On\s+\w+,\s+\d{1,2}/\d{1,2}/\d{2,4}\s+at\s+",  # On Saturday, 05/16/26 at
        r"^On\s+\w+,\s+\w+\s+\d{1,2},\s+\d{4}\s+at\s+",  # On Fri, May 15, 2026 at
        r"^>",  # Standard quote lines
        r"^Sent from \[",  # "Sent from [Proton Mail]..."
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
            break  # Stop at first quote marker — everything after is reply chain
        clean_lines.append(line)
    return "\n".join(clean_lines)


# ── Date extraction from natural language ──────────────────────────────────

def _extract_dates_from_text(text: str, reference_date: datetime) -> list[datetime]:
    """Extract date references from email text.

    Handles:
      - "20 may", "may 20", "20th may", "may 20th"
      - "20th", "19th" (bare ordinals — infer month from reference_date)
      - "20/05", "05/20", "2026-05-20"
      - "today", "tomorrow", "day after tomorrow"
      - Day names: "monday", "tuesday", etc.
    """
    text_lower = text.lower()
    found: list[datetime] = []
    ref_year = reference_date.year
    ref_month = reference_date.month

    # ── Pattern 1: "20 may", "20th may", "20th of may" ──
    ordinal_with_month = set()
    for m in re.finditer(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?("
        + "|".join(_MONTH_MAP.keys())
        + r")\b",
        text_lower,
    ):
        day, month_name = int(m.group(1)), _MONTH_MAP[m.group(2)]
        ordinal_with_month.add(m.group(1))  # Track which numbers had month names
        try:
            found.append(datetime(ref_year, month_name, day))
        except ValueError:
            pass

    # ── Pattern 2: "may 20", "may 20th" ──
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

    # ── Pattern 3: Bare ordinals "19th", "20th" (no month name) ──
    #     Infer the month from the email's reference date.
    for m in re.finditer(r"\b(\d{1,2})(st|nd|rd|th)\b", text_lower):
        day_str = m.group(1)
        if day_str in ordinal_with_month:
            continue  # Already matched with a month name above
        day = int(day_str)
        if 1 <= day <= 31:
            try:
                # Try current month first
                candidate = datetime(ref_year, ref_month, day)
                # If the date is in the past, try next month
                if candidate.date() < reference_date.date():
                    next_month = ref_month + 1 if ref_month < 12 else 1
                    next_year = ref_year if ref_month < 12 else ref_year + 1
                    candidate = datetime(next_year, next_month, day)
                found.append(candidate)
            except ValueError:
                pass

    # ── Pattern 4: ISO-style "2026-05-20" ──
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", text_lower):
        try:
            found.append(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass

    # ── Pattern 5: "today", "tomorrow", "day after tomorrow" ──
    if re.search(r"\btoday\b", text_lower):
        found.append(reference_date.replace(hour=0, minute=0, second=0, microsecond=0))
    if re.search(r"\btomorrow\b", text_lower):
        found.append((reference_date + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0))
    if re.search(r"\bday after tomorrow\b", text_lower):
        found.append((reference_date + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0))

    # ── Pattern 6: Day names → next occurrence ──
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

    # "4pm", "4 pm", "4:30pm"
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text_lower)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        if m.group(3) == "pm" and hour != 12:
            hour += 12
        elif m.group(3) == "am" and hour == 12:
            hour = 0
        return (hour, minute)

    # "16:00", "14:30"
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", text_lower)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return (hour, minute)

    return None


# ── Relevance checks ──────────────────────────────────────────────────────

def _email_mentions_time_or_dates(email: Email) -> bool:
    """Check if the email body references times, dates, or meeting concepts."""
    # Use ONLY the non-quoted part of the email
    clean_body = _strip_quoted_text(email.body)
    text = f"{email.subject} {clean_body}".lower()

    patterns = [
        r"\b(today|tomorrow|tonight|day after tomorrow)\b",
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\b(meeting|standup|sync|call|demo|review|retro|planning|deadline|meet)\b",
        r"\b\d{1,2}:\d{2}\b",
        r"\b\d{1,2}(am|pm)\b",
        r"\b(schedule|calendar|appointment|event|free|available|busy)\b",
        r"\b\d{1,2}(st|nd|rd|th)\b",  # Bare ordinals like "19th"
    ]
    # Month names
    month_pattern = r"\b(" + "|".join(_MONTH_MAP.keys()) + r")\b"
    patterns.append(month_pattern)

    return any(re.search(p, text) for p in patterns)


def _date_overlap(email: Email, event: CalendarEvent) -> bool:
    """Check if dates mentioned in the email match the event date.

    IMPORTANT: We strip quoted text before extracting dates to avoid
    false positives from reply chain headers like "On Saturday, 05/16/26".
    """
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
    """Check if meaningful keywords from the email match the event.

    Uses ONLY the non-quoted part of the email to avoid false matches
    from reply chain content.
    """
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
    """Return only calendar events that are relevant to this email.

    Relevance is determined by (in priority order):
    1. Date overlap — email mentions a date that matches an event date
    2. Attendee overlap — sender/recipients appear in event attendees
    3. Keyword overlap — shared meaningful words between email and event

    Gate: if the email doesn't mention any time/date/meeting concepts,
    no events are injected at all.
    """
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


def _format_relevant_context(events: list[CalendarEvent]) -> str:
    """Format only relevant events for the prompt, or a clear 'none' message."""
    if not events:
        return "--- Calendar context ---\nNo relevant calendar events for this email."

    lines = ["--- Calendar context (events related to this email) ---"]
    for ev in events:
        date_str = ev.start.strftime("%a %b %d, %H:%M")
        end_str = ev.end.strftime("%H:%M") if ev.end and ev.end != ev.start else ""
        time_display = "All day" if ev.is_all_day else f"{date_str}–{end_str}" if end_str else date_str
        attendees = ", ".join(ev.attendees) if ev.attendees else "just you"
        location = f" @ {ev.location}" if ev.location else ""
        lines.append(f"  - {ev.title}: {time_display}{location} (with {attendees})")
        if ev.description:
            lines.append(f"    Note: {ev.description[:100]}")
    return "\n".join(lines)


# ── Auto-event creation from meeting emails ───────────────────────────────

def extract_meeting_event(email: Email, classification: Classification) -> CalendarEvent | None:
    """Extract a calendar event from a classified meeting email.

    If the email is classified as a meeting and mentions dates/times,
    auto-create a calendar event so the user's calendar reflects their
    availability. Returns None if no date can be extracted.
    """
    if classification.category.value != "meeting":
        return None

    clean_body = _strip_quoted_text(email.body)
    text = f"{email.subject} {clean_body}"

    dates = _extract_dates_from_text(text, email.timestamp)
    if not dates:
        return None

    # Use the most likely date (first found from the non-quoted text)
    meeting_date = dates[0]

    # Try to extract a time
    time_info = _extract_time_from_text(text)
    if time_info:
        hour, minute = time_info
        meeting_start = meeting_date.replace(hour=hour, minute=minute)
        meeting_end = meeting_start + timedelta(hours=1)  # Default 1hr
        is_all_day = False
    else:
        meeting_start = meeting_date
        meeting_end = meeting_date.replace(hour=23, minute=59)
        is_all_day = True

    sender_name = email.sender.split("@")[0].replace(".", " ").title()
    return CalendarEvent(
        id=f"auto-{email.id[:12]}",
        title=f"Meeting: {sender_name} — {email.subject[:40]}",
        start=meeting_start,
        end=meeting_end,
        description=f"Auto-created from email: {email.subject}\nFrom: {email.sender}",
        color="#f59e0b",  # Amber for auto-created
        attendees=[email.sender] + email.recipients[:5],
        is_all_day=is_all_day,
    )


# ── Classification ─────────────────────────────────────────────────────────

async def classify(
    email: Email,
    calendar_events: list[CalendarEvent] | None = None,
) -> Classification:
    """Classify an email by priority and category.

    Uses smart filtering to only inject relevant calendar context.
    """
    privacy = PrivacyGateway()

    relevant_events = filter_relevant_events(email, calendar_events or [])
    cal_ctx = _format_relevant_context(relevant_events)

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
    safe_store_pii_mappings(email.id, "classification", privacy.mappings)
    log.info(
        "classified",
        extra={
            "email_id": email.id,
            "priority": parsed.priority.value,
            "category": parsed.category.value,
            "relevant_events": len(relevant_events),
            "total_events": len(calendar_events or []),
            "pii_masked": bool(privacy.mappings),
            "pii_types": sorted({mapping.entity_type.lower() for mapping in privacy.mappings}),
        },
    )
    return parsed


def _parse_classification(raw: str) -> Classification:
    """Parse the LLM's JSON output into a Classification model."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])

    data = json.loads(text)
    return Classification.model_validate(data)
