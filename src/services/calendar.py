"""Calendar context provider with local CRUD support."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.models.email import CalendarEvent


def load_events(data_file: Path) -> list[CalendarEvent]:
    """Read calendar events from a JSON file."""
    with open(data_file, encoding="utf-8") as f:
        raw = json.load(f)
    events = []
    for entry in raw:
        if not entry.get("id"):
            entry["id"] = f"cal-{uuid4().hex[:8]}"
        events.append(CalendarEvent.model_validate(entry))
    return events


def _as_utc(dt: datetime) -> datetime:
    """Return a timezone-aware datetime, assuming UTC if naive."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def get_upcoming_events(
    events: list[CalendarEvent],
    around: datetime,
    window_days: int = 7,
) -> list[CalendarEvent]:
    """Return events within ``window_days`` of the given timestamp."""
    around = _as_utc(around)
    start = around - timedelta(days=1)
    end = around + timedelta(days=window_days)
    return [e for e in events if start <= _as_utc(e.start) <= end]


def get_events_for_date(
    events: list[CalendarEvent],
    date: datetime,
) -> list[CalendarEvent]:
    """Return events on a specific date."""
    return [
        e for e in events
        if e.start.date() == date.date()
    ]


def create_event(
    events: list[CalendarEvent],
    data: dict[str, Any],
) -> CalendarEvent:
    """Create a new local calendar event."""
    if not data.get("id"):
        data["id"] = f"cal-{uuid4().hex[:8]}"
    event = CalendarEvent.model_validate(data)
    events.append(event)
    return event


def update_event(
    events: list[CalendarEvent],
    event_id: str,
    data: dict[str, Any],
) -> CalendarEvent | None:
    """Update an existing calendar event by ID."""
    for i, ev in enumerate(events):
        if ev.id == event_id:
            merged = {**ev.model_dump(mode="json"), **data, "id": event_id}
            updated = CalendarEvent.model_validate(merged)
            events[i] = updated
            return updated
    return None


def delete_event(
    events: list[CalendarEvent],
    event_id: str,
) -> bool:
    """Delete a calendar event by ID. Returns True if found."""
    for i, ev in enumerate(events):
        if ev.id == event_id:
            events.pop(i)
            return True
    return False


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