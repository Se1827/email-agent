"""Email classification service — assigns priority and category via LLM.

Uses LangChain ChatGroq with smart calendar-context filtering: only
calendar events that are semantically relevant to the email are injected
into the prompt.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime

from src.llm import client as llm
from src.llm.prompts import CLASSIFY_SYSTEM, CLASSIFY_USER
from src.models.email import CalendarEvent, Classification, Email
from src.services.pii import PrivacyGateway
from src.storage import safe_store_pii_mappings

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Smart calendar-context filtering
# ---------------------------------------------------------------------------

def _extract_email_keywords(email: Email) -> set[str]:
    """Extract meaningful keywords from the email for matching."""
    text = f"{email.subject} {email.body}".lower()
    # Remove common stop words and extract tokens
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "and", "or", "but", "if",
        "then", "else", "when", "at", "by", "for", "with", "about", "from",
        "to", "in", "on", "of", "it", "its", "this", "that", "these", "those",
        "i", "me", "my", "we", "our", "you", "your", "he", "she", "they",
        "hi", "hello", "hey", "thanks", "thank", "regards", "best", "dear",
        "please", "kindly", "not", "no", "yes",
    }
    words = set(re.findall(r"[a-z]{3,}", text))
    return words - stop_words


def _email_mentions_time(email: Email) -> bool:
    """Check if the email body references times/dates/deadlines."""
    patterns = [
        r"\b(today|tomorrow|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\b(meeting|standup|sync|call|demo|review|retro|planning|deadline)\b",
        r"\b\d{1,2}:\d{2}\b",  # time references like 2:30
        r"\b\d{1,2}(am|pm)\b",  # 2pm style
        r"\b(schedule|calendar|appointment|event)\b",
    ]
    text = f"{email.subject} {email.body}".lower()
    return any(re.search(p, text) for p in patterns)


def _attendee_overlap(email: Email, event: CalendarEvent) -> bool:
    """Check if email sender/recipients overlap with event attendees."""
    email_people = {email.sender.lower()} | {r.lower() for r in email.recipients}
    event_people = {a.lower() for a in event.attendees}
    return bool(email_people & event_people)


def _keyword_overlap(email_keywords: set[str], event: CalendarEvent) -> bool:
    """Check if meaningful keywords from the email match the event."""
    event_text = f"{event.title} {event.description}".lower()
    event_words = set(re.findall(r"[a-z]{3,}", event_text))
    # Require at least 2 overlapping meaningful words, or 1 if it's
    # a distinctive word (>5 chars)
    overlap = email_keywords & event_words
    distinctive = {w for w in overlap if len(w) > 5}
    return len(overlap) >= 2 or len(distinctive) >= 1


def filter_relevant_events(
    email: Email,
    events: list[CalendarEvent],
) -> list[CalendarEvent]:
    """Return only calendar events that are relevant to this email.

    Relevance is determined by:
    1. Attendee overlap (sender/recipients match event attendees)
    2. Keyword overlap (email text shares meaningful words with event)
    3. Only considered if email itself references time/meeting concepts

    If the email doesn't mention anything time-related, no events are
    injected — this prevents irrelevant calendar context from polluting
    classification and drafting.
    """
    if not events:
        return []

    # If the email doesn't even mention time/meeting concepts,
    # calendar context is irrelevant
    if not _email_mentions_time(email):
        return []

    email_keywords = _extract_email_keywords(email)
    relevant: list[CalendarEvent] = []

    for event in events:
        if _attendee_overlap(email, event):
            relevant.append(event)
        elif _keyword_overlap(email_keywords, event):
            relevant.append(event)

    return relevant


def _format_relevant_context(events: list[CalendarEvent]) -> str:
    """Format only relevant events for the prompt, or a clear 'none' message."""
    if not events:
        return "--- Calendar context ---\nNo relevant calendar events for this email."

    lines = ["--- Calendar context (events related to this email) ---"]
    for ev in events:
        date_str = ev.start.strftime("%a %b %d, %H:%M")
        attendees = ", ".join(ev.attendees) if ev.attendees else "just you"
        lines.append(f"  - {ev.title} on {date_str} (with {attendees})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

async def classify(
    email: Email,
    calendar_events: list[CalendarEvent] | None = None,
) -> Classification:
    """Classify an email by priority and category.

    Uses smart filtering to only inject relevant calendar context.
    """
    privacy = PrivacyGateway()

    # Smart filter: only inject relevant events
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
    """Parse the LLM's JSON output into a Classification model.

    Handles minor formatting issues like markdown code fences.
    """
    text = raw.strip()
    if text.startswith("```"):
        # Strip ```json ... ``` wrappers if the model adds them.
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])

    data = json.loads(text)
    return Classification.model_validate(data)
