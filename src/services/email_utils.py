"""Shared email utility functions.

Extracted from classifier.py to avoid circular imports when agents
need ``filter_relevant_events`` or ``_strip_quoted_text``.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.email import CalendarEvent, Email

log = logging.getLogger(__name__)

# ── Month name maps ────────────────────────────────────────────────────────
_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5,
    "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def strip_quoted_text(body: str) -> str:
    """Remove quoted reply chains from the email body."""
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
        if any(re.match(sep, stripped, re.IGNORECASE) for sep in separators):
            break
        clean_lines.append(line)
    return "\n".join(clean_lines)


def extract_dates_from_text(text: str, reference_date: datetime) -> list[datetime]:
    """Extract date references from email text."""
    text_lower = text.lower()
    found: list[datetime] = []
    ref_year = reference_date.year
    ref_month = reference_date.month

    ordinal_with_month: set[str] = set()
    for m in re.finditer(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?("
        + "|".join(_MONTH_MAP.keys()) + r")\b", text_lower,
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


def extract_time_from_text(text: str) -> tuple[int, int] | None:
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


def email_mentions_time_or_dates(email: "Email") -> bool:
    """Check if the email body references times, dates, or meeting concepts."""
    clean_body = strip_quoted_text(email.body)
    text = f"{email.subject} {clean_body}".lower()
    patterns = [
        r"\b(today|tomorrow|tonight|day after tomorrow)\b",
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\b(meeting|standup|sync|call|demo|review|retro|planning|deadline|meet)\b",
        r"\b\d{1,2}:\d{2}\b", r"\b\d{1,2}(am|pm)\b",
        r"\b(schedule|calendar|appointment|event|free|available|busy)\b",
        r"\b\d{1,2}(st|nd|rd|th)\b",
        r"\b(" + "|".join(_MONTH_MAP.keys()) + r")\b",
    ]
    return any(re.search(p, text) for p in patterns)


def date_overlap(email: "Email", event: "CalendarEvent") -> bool:
    """Check if dates mentioned in the email match the event date."""
    clean_body = strip_quoted_text(email.body)
    text = f"{email.subject} {clean_body}"
    mentioned_dates = extract_dates_from_text(text, email.timestamp)
    if not mentioned_dates:
        return False
    event_date = event.start.date()
    return any(d.date() == event_date for d in mentioned_dates)


def attendee_overlap(email: "Email", event: "CalendarEvent") -> bool:
    """Check if email sender/recipients overlap with event attendees."""
    email_people = {email.sender.lower()} | {r.lower() for r in email.recipients}
    event_people = {a.lower() for a in event.attendees}
    return bool(email_people & event_people)


def keyword_overlap(email: "Email", event: "CalendarEvent") -> bool:
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
    clean_body = strip_quoted_text(email.body)
    email_text = f"{email.subject} {clean_body}".lower()
    email_words = set(re.findall(r"[a-z]{3,}", email_text)) - stop_words
    event_text = f"{event.title} {event.description}".lower()
    event_words = set(re.findall(r"[a-z]{3,}", event_text)) - stop_words
    overlap = email_words & event_words
    distinctive = {w for w in overlap if len(w) > 5}
    return len(overlap) >= 2 or len(distinctive) >= 1


def filter_relevant_events(
    email: "Email", events: list["CalendarEvent"],
) -> list["CalendarEvent"]:
    """Return only calendar events that are relevant to this email."""
    if not events:
        return []
    if not email_mentions_time_or_dates(email):
        return []
    relevant: list["CalendarEvent"] = []
    seen_ids: set[str] = set()
    for event in events:
        if event.id in seen_ids:
            continue
        if date_overlap(email, event) or attendee_overlap(email, event) or keyword_overlap(email, event):
            relevant.append(event)
            seen_ids.add(event.id)
    log.info("calendar_relevance_filter", extra={
        "email_id": email.id, "total_events": len(events),
        "relevant_events": len(relevant),
    })
    return relevant
