"""Deterministic calendar conflict detection and free-slot finding.

This module contains **zero LLM calls**. It is the shared foundation that
both Classic Mode (calls directly) and AI-Rich Mode (exposes as agent tools)
rely on for accurate, testable calendar arithmetic.

Key design decisions:
  - Wall-clock comparison: timezone info is stripped so "4 PM" in a
    calendar event matches "4 PM" extracted from an email, regardless
    of stored UTC offsets.
  - All-day events block the entire calendar date.
  - Free-slot finding respects configurable working hours.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from src.models.email import CalendarEvent

log = logging.getLogger(__name__)


# ── Data classes ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ConflictResult:
    """Describes a single conflict between a candidate window and an event."""
    event: CalendarEvent
    reason: str  # "all_day_overlap" | "time_overlap"
    candidate_start: datetime
    candidate_end: datetime


@dataclass(frozen=True)
class TimeSlot:
    """A free window on a given date."""
    start: datetime
    end: datetime

    @property
    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() / 60)


# ── Wall-clock helpers ─────────────────────────────────────────────────────


def wall_clock(dt: datetime) -> datetime:
    """Strip timezone info to get the local wall-clock time as a naive datetime.

    This is intentional: calendar events from calendar.json are stored in
    local time with offset (e.g. 16:00+05:30) and emails produce naive
    datetimes from natural-language extraction (e.g. "4pm" → 16:00 naive).
    Converting both to UTC would shift them apart. Instead we compare them
    as wall-clock times — "4pm is 4pm" regardless of timezone.
    """
    return dt.replace(tzinfo=None)


# ── Conflict detection ─────────────────────────────────────────────────────


def find_conflicts(
    candidate_start: datetime,
    candidate_end: datetime,
    events: list[CalendarEvent],
    *,
    candidate_is_all_day: bool = False,
) -> list[ConflictResult]:
    """Return all events that conflict with the candidate time window.

    This is the core conflict engine. Both ``has_calendar_conflict`` (for
    CalendarEvent objects) and ``check_full_calendar_conflict`` (for raw
    datetimes) delegate here.
    """
    cand_s = wall_clock(candidate_start)
    cand_e = wall_clock(candidate_end)
    if candidate_is_all_day:
        cand_e = cand_s.replace(hour=23, minute=59)
    cand_date = cand_s.date()

    conflicts: list[ConflictResult] = []
    for ev in events:
        ev_s = wall_clock(ev.start)
        if ev_s.date() != cand_date:
            continue
        ev_e = wall_clock(ev.end) if ev.end else ev_s + timedelta(hours=1)

        reason: str | None = None
        if ev.is_all_day:
            reason = "all_day_overlap"
        elif candidate_is_all_day:
            reason = "all_day_overlap"
        elif cand_s < ev_e and ev_s < cand_e:
            reason = "time_overlap"

        if reason:
            conflicts.append(ConflictResult(
                event=ev,
                reason=reason,
                candidate_start=cand_s,
                candidate_end=cand_e,
            ))

    if conflicts:
        log.info(
            "conflicts_found",
            extra={
                "candidate_window": f"{cand_s.isoformat()}–{cand_e.isoformat()}",
                "conflict_count": len(conflicts),
                "conflict_titles": [c.event.title for c in conflicts],
            },
        )
    return conflicts


def has_calendar_conflict(
    candidate: CalendarEvent,
    existing_events: list[CalendarEvent],
) -> CalendarEvent | None:
    """Return the first existing event that conflicts with the candidate.

    Convenience wrapper around ``find_conflicts`` that works with
    CalendarEvent objects and returns a single event (backward-compatible
    with the old classifier.py API).
    """
    candidate_start = wall_clock(candidate.start)
    candidate_end = (
        wall_clock(candidate.end) if candidate.end
        else candidate_start + timedelta(hours=1)
    )

    # Exclude self
    filtered = [ev for ev in existing_events if ev.id != candidate.id]

    results = find_conflicts(
        candidate_start,
        candidate_end,
        filtered,
        candidate_is_all_day=candidate.is_all_day,
    )
    return results[0].event if results else None


def check_full_calendar_conflict(
    cand_start: datetime,
    cand_end: datetime,
    candidate_is_all_day: bool,
    all_events: list[CalendarEvent],
) -> CalendarEvent | None:
    """Check the full calendar for any event that blocks the candidate window.

    Lighter wrapper that works with raw start/end datetimes instead of
    requiring a CalendarEvent.
    """
    results = find_conflicts(
        cand_start,
        cand_end,
        all_events,
        candidate_is_all_day=candidate_is_all_day,
    )
    return results[0].event if results else None


# ── Free-slot finding ──────────────────────────────────────────────────────


def find_free_slots(
    date: datetime,
    events: list[CalendarEvent],
    *,
    working_start_hour: int = 9,
    working_end_hour: int = 18,
    min_duration_minutes: int = 30,
    constraints: list[str] | None = None,
) -> list[TimeSlot]:
    """Find free time windows on a given date, considering existing events.

    Only looks within working hours. Returns slots of at least
    ``min_duration_minutes`` length.

    ``constraints`` is a list of natural-language scheduling constraints
    from user preferences (e.g. "no meetings before 10am", "lunch 12-1pm").
    These are parsed heuristically to narrow the working window.
    """
    # ── Apply constraints to working hours ─────────────────────────────
    if constraints:
        import re
        for c in constraints:
            c_lower = c.lower()
            # "no meetings before Xam/pm"
            m = re.search(r"before\s+(\d{1,2})\s*(am|pm)?", c_lower)
            if m:
                h = int(m.group(1))
                if m.group(2) == "pm" and h != 12:
                    h += 12
                working_start_hour = max(working_start_hour, h)
            # "no meetings after Xpm"
            m = re.search(r"after\s+(\d{1,2})\s*(am|pm)?", c_lower)
            if m:
                h = int(m.group(1))
                if m.group(2) == "pm" and h != 12:
                    h += 12
                working_end_hour = min(working_end_hour, h)

    target_date = date.date()

    # Collect busy windows on the target date (wall-clock times)
    busy: list[tuple[datetime, datetime]] = []
    for ev in events:
        ev_s = wall_clock(ev.start)
        if ev_s.date() != target_date:
            continue
        if ev.is_all_day:
            # All-day event blocks the entire day
            return []
        ev_e = wall_clock(ev.end) if ev.end else ev_s + timedelta(hours=1)
        busy.append((ev_s, ev_e))

    # ── Add lunch block if user has that constraint ────────────────────
    if constraints:
        for c in constraints:
            if "lunch" in c.lower():
                import re
                m = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})", c)
                if m:
                    lunch_s = datetime(target_date.year, target_date.month, target_date.day, int(m.group(1)), 0)
                    lunch_e = datetime(target_date.year, target_date.month, target_date.day, int(m.group(2)), 0)
                    busy.append((lunch_s, lunch_e))

    # Sort by start time
    busy.sort(key=lambda pair: pair[0])

    # Walk through the working hours and find gaps
    day_start = datetime(target_date.year, target_date.month, target_date.day, working_start_hour, 0)
    day_end = datetime(target_date.year, target_date.month, target_date.day, working_end_hour, 0)
    min_delta = timedelta(minutes=min_duration_minutes)

    free: list[TimeSlot] = []
    cursor = day_start

    for busy_start, busy_end in busy:
        # Clamp busy window to working hours
        busy_start = max(busy_start, day_start)
        busy_end = min(busy_end, day_end)

        if busy_start <= cursor:
            cursor = max(cursor, busy_end)
            continue

        gap = busy_start - cursor
        if gap >= min_delta:
            free.append(TimeSlot(start=cursor, end=busy_start))
        cursor = max(cursor, busy_end)

    # Trailing free time after last event
    if cursor < day_end and (day_end - cursor) >= min_delta:
        free.append(TimeSlot(start=cursor, end=day_end))

    log.info(
        "free_slots_found",
        extra={
            "date": target_date.isoformat(),
            "slot_count": len(free),
            "busy_count": len(busy),
        },
    )
    return free


# ── Context formatting ─────────────────────────────────────────────────────


def format_conflict_context(
    events: list[CalendarEvent],
    candidate_start: datetime | None = None,
    candidate_end: datetime | None = None,
    *,
    all_events: list[CalendarEvent] | None = None,
    candidate_is_all_day: bool = False,
    source_email_id: str | None = None,
) -> str:
    """Format relevant events for the prompt with explicit conflict/free labels.

    If candidate_start is provided, each event is labelled CONFLICT or free
    so the LLM does not have to infer availability.

    When ``all_events`` is supplied the function also checks for conflicts
    against the *full* calendar — not just the semantically-relevant subset.
    """
    if candidate_start is not None:
        cand_s = wall_clock(candidate_start)
        if candidate_is_all_day:
            cand_e = cand_s.replace(hour=23, minute=59)
        else:
            cand_e = wall_clock(candidate_end) if candidate_end else cand_s + timedelta(hours=1)
    else:
        cand_s = cand_e = None

    # ── Build the event list section ───────────────────────────────────
    if not events and cand_s is None:
        return "--- Calendar context ---\nYou have no relevant calendar events. You are free."

    lines = ["--- Calendar context (events related to this email) ---"]
    any_conflict = False
    for ev in events:
        # Skip events auto-created from the same email being classified
        is_self_event = source_email_id and ev.source_email_id == source_email_id
        date_str = ev.start.strftime("%a %b %d, %H:%M")
        end_str = ev.end.strftime("%H:%M") if ev.end and ev.end != ev.start else ""
        time_display = "All day" if ev.is_all_day else f"{date_str}–{end_str}" if end_str else date_str
        attendees = ", ".join(ev.attendees) if ev.attendees else "just you"
        location = f" @ {ev.location}" if ev.location else ""

        if is_self_event:
            label = " [ALREADY SCHEDULED from this email]"
        elif cand_s is not None:
            ev_s = wall_clock(ev.start)
            ev_e = wall_clock(ev.end) if ev.end else ev_s + timedelta(hours=1)
            same_day = ev_s.date() == cand_s.date()
            if ev.is_all_day and same_day:
                label = " [CONFLICT: all-day event]"
                any_conflict = True
            elif same_day and cand_s < ev_e and ev_s < cand_e:
                label = " [CONFLICT: time overlaps]"
                any_conflict = True
            else:
                label = " [no conflict]"
        else:
            label = ""

        lines.append(f"  - {ev.title}: {time_display}{location} (with {attendees}){label}")
        if ev.description:
            lines.append(f"    Note: {ev.description[:100]}")

    # ── Full-calendar conflict check ──────────────────────────────────
    if cand_s is not None and not any_conflict and all_events:
        # Exclude self-events from the full-calendar conflict check
        check_events = [
            ev for ev in all_events
            if not (source_email_id and ev.source_email_id == source_email_id)
        ]
        full_conflict = check_full_calendar_conflict(
            cand_s, cand_e, candidate_is_all_day, check_events,
        )
        if full_conflict:
            any_conflict = True
            fc_title = full_conflict.title
            fc_display = "All day" if full_conflict.is_all_day else full_conflict.start.strftime("%H:%M")
            lines.append(f"  - {fc_title}: {fc_display} [CONFLICT: blocks requested time]")

    # ── Explicit availability verdict ─────────────────────────────────
    if cand_s is not None:
        date_label = cand_s.strftime("%A, %b %d")
        if any_conflict:
            lines.append(f"AVAILABILITY: You are NOT free on {date_label}. You MUST decline or propose an alternative.")
        else:
            lines.append(f"AVAILABILITY: You ARE free on {date_label}. You can accept the proposed time.")
    elif not events:
        lines.append("No relevant calendar events found — you appear to be free.")

    return "\n".join(lines)
