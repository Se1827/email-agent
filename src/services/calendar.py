"""Mock calendar context provider."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from src.models.email import CalendarEvent


def load_events(data_file: Path) -> list[CalendarEvent]:
    """Read calendar events from a JSON file."""
    with open(data_file) as f:
        raw = json.load(f)
    return [CalendarEvent.model_validate(entry) for entry in raw]


def get_upcoming_events(
    events: list[CalendarEvent],
    around: datetime,
    window_days: int = 7,
) -> list[CalendarEvent]:
    """Return events within ``window_days`` of the given timestamp."""
    start = around - timedelta(days=1)
    end = around + timedelta(days=window_days)
    return [e for e in events if start <= e.start <= end]


def format_calendar_context(events: list[CalendarEvent]) -> str:
    """Render a list of calendar events as a human-readable block for prompts."""
    if not events:
        return "No upcoming calendar events."

    lines = ["Upcoming calendar events:"]
    for ev in events:
        date_str = ev.start.strftime("%a %b %d, %H:%M")
        attendees = ", ".join(ev.attendees) if ev.attendees else "just you"
        lines.append(f"  - {ev.title} on {date_str} (with {attendees})")
    return "\n".join(lines)
