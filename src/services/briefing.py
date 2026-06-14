"""Pre-meeting brief — AI-generated context for upcoming meetings.

Gathers all related emails, action items, and sender profiles for a
calendar event and produces a one-page prep brief.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.llm import client as llm
from src.services.search import search_similar_emails
from src.services.memory import get_sender_profile
from src.services.actions import get_action_items

log = logging.getLogger(__name__)

_BRIEF_SYSTEM = """\
You are a meeting preparation assistant. Given context about an upcoming meeting,
produce a structured brief.

Respond ONLY with JSON (no markdown):
{
  "meeting_title": "...",
  "key_context": ["point 1", "point 2"],
  "attendee_notes": [{"name": "...", "note": "..."}],
  "open_items": ["item 1"],
  "suggested_talking_points": ["point 1", "point 2"],
  "one_line": "Brief one-line summary of what to prepare for."
}
"""


async def generate_meeting_brief(
    event_title: str,
    event_description: str | None = None,
    attendees: list[str] | None = None,
    start_time: str | None = None,
) -> dict[str, Any]:
    """Generate a pre-meeting brief for a calendar event."""

    # ── Gather context ─────────────────────────────────────────────────
    related_emails = search_similar_emails(
        f"{event_title} {event_description or ''}", limit=5,
    )

    attendee_notes = []
    for attendee in (attendees or []):
        profile = get_sender_profile(attendee)
        if profile:
            attendee_notes.append({
                "name": profile.display_name or attendee,
                "relationship": profile.relationship,
                "interactions": profile.interaction_count,
            })

    pending_actions = get_action_items(status="pending")
    relevant_actions = [
        a for a in pending_actions
        if event_title.lower() in a.get("description", "").lower()
    ][:5]

    # ── Build prompt ───────────────────────────────────────────────────
    prompt = f"Meeting: {event_title}\n"
    if start_time:
        prompt += f"Time: {start_time}\n"
    if event_description:
        prompt += f"Description: {event_description[:300]}\n"

    if attendee_notes:
        prompt += "\nAttendees:\n"
        for a in attendee_notes:
            prompt += f"  - {a['name']} ({a['relationship']}, {a['interactions']} interactions)\n"

    if related_emails:
        prompt += "\nRelated emails:\n"
        for e in related_emails:
            prompt += f"  - {e['summary'][:80]}\n"

    if relevant_actions:
        prompt += "\nRelated action items:\n"
        for a in relevant_actions:
            prompt += f"  - {a['description']}\n"

    try:
        raw = await llm.chat(
            messages=[
                {"role": "system", "content": _BRIEF_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=500,
        )

        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])

        return json.loads(text)

    except Exception:
        log.exception("meeting_brief_failed")
        return {
            "meeting_title": event_title,
            "key_context": [e["summary"][:80] for e in related_emails[:3]],
            "attendee_notes": attendee_notes,
            "open_items": [a["description"] for a in relevant_actions],
            "suggested_talking_points": [],
            "one_line": f"Prepare for: {event_title}",
        }
