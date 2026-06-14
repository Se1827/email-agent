"""Daily digest — AI-generated summary of the day's email priorities.

Provides a ranked summary of pending emails, grouped by theme,
with nudges for overdue action items and upcoming meetings.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from src.llm import client as llm
from src.services.actions import get_action_items

log = logging.getLogger(__name__)

_DIGEST_SYSTEM = """\
You are an email productivity assistant generating a daily brief.
Given pending emails and action items, produce a structured daily digest.

Respond ONLY with JSON (no markdown):
{
  "greeting": "Good morning! Here's your daily brief.",
  "priority_emails": [
    {"subject": "...", "sender": "...", "why": "...", "priority": "high"}
  ],
  "themes": [
    {"theme": "Project X", "count": 3, "summary": "..."}
  ],
  "nudges": ["Overdue: Reply to Alice about deadline"],
  "calendar_today": ["10:00 — Team standup", "14:00 — Client call"],
  "one_line": "You have 5 emails needing attention, 2 are high priority."
}
"""


async def generate_daily_digest(
    emails: list[dict[str, Any]],
    calendar_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate a daily digest from pending emails and calendar.

    Parameters
    ----------
    emails : list[dict]
        Each dict should have: subject, sender, priority, category, timestamp
    calendar_events : list[dict] | None
        Today's calendar events with: title, start, end
    """
    # ── Get pending action items ───────────────────────────────────────
    pending_actions = get_action_items(status="pending")

    # ── Build prompt context ───────────────────────────────────────────
    email_summaries = []
    for e in emails[:20]:  # Cap at 20 most recent
        email_summaries.append(
            f"- [{e.get('priority', '?').upper()}] {e.get('subject', 'No subject')} "
            f"from {e.get('sender', 'unknown')}"
        )

    action_summaries = []
    for a in pending_actions[:10]:
        due = a.get("due_date", "no due date")
        action_summaries.append(f"- {a['description']} (due: {due})")

    cal_summaries = []
    if calendar_events:
        for ev in calendar_events[:10]:
            cal_summaries.append(f"- {ev.get('start', '?')} — {ev.get('title', '?')}")

    prompt = (
        f"Today: {datetime.now().strftime('%A, %B %d, %Y')}\n\n"
        f"Pending emails ({len(emails)}):\n"
        + "\n".join(email_summaries or ["(none)"])
        + f"\n\nPending action items ({len(pending_actions)}):\n"
        + "\n".join(action_summaries or ["(none)"])
        + f"\n\nToday's calendar ({len(cal_summaries)}):\n"
        + "\n".join(cal_summaries or ["(none)"])
    )

    try:
        raw = await llm.chat(
            messages=[
                {"role": "system", "content": _DIGEST_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=600,
        )

        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])

        return json.loads(text)

    except Exception:
        log.exception("digest_generation_failed")
        return {
            "greeting": "Here's your daily overview.",
            "priority_emails": [],
            "themes": [],
            "nudges": [a["description"] for a in pending_actions[:3]],
            "calendar_today": [ev.get("title", "?") for ev in (calendar_events or [])[:5]],
            "one_line": f"You have {len(emails)} emails and {len(pending_actions)} pending actions.",
        }
