"""Test the fixed calendar relevance filter — covers the exact failing scenarios."""
from datetime import datetime, timezone, timedelta
from src.models.email import Email, CalendarEvent, Classification, Priority, Category
from src.services.classifier import (
    filter_relevant_events,
    _extract_dates_from_text,
    _strip_quoted_text,
    extract_meeting_event,
)

# ── Test 1: Strip quoted text ─────────────────────────────────────────────

reply_body = """What about 19th 4pm??

Sent from [Proton Mail](https://proton.me/mail/home) for Android.

-------- Original Message --------
On Saturday, 05/16/26 at 01:18 modibhakt@elektrine.com wrote:

> nope
>
> On Fri, May 15, 2026 at 07:01 PM, "Sus Kid" wrote:
>
> Are you free on 20 may?? If yes we can meet
>
> Sent from [Proton Mail](https://proton.me/mail/home) for Android."""

clean = _strip_quoted_text(reply_body)
assert "19th 4pm" in clean
assert "05/16/26" not in clean, f"Quoted date not stripped! clean={clean!r}"
assert "May 15, 2026" not in clean
print("PASS  Strip quoted text: reply chain dates removed")

# ── Test 2: Bare ordinal "19th" -> May 19 ──────────────────────────────────

ref = datetime(2026, 5, 15, 19, 0, 0)
dates = _extract_dates_from_text("What about 19th 4pm??", ref)
assert any(d.month == 5 and d.day == 19 for d in dates), f"'19th' not extracted: {dates}"
print("PASS  Bare ordinal '19th' -> May 19")

# ── Test 3: "20 may" still works ──────────────────────────────────────────

dates2 = _extract_dates_from_text("Are you free on 20 may?", ref)
assert any(d.month == 5 and d.day == 20 for d in dates2), f"'20 may' not extracted: {dates2}"
print("PASS  '20 may' still works")

# ── Test 4: Dates from quoted text should NOT be extracted ─────────────────

full_body_dates = _extract_dates_from_text(reply_body, ref)
stripped_dates = _extract_dates_from_text(clean, ref)
print(f"  Full body dates: {[(d.month, d.day) for d in full_body_dates]}")
print(f"  Stripped dates: {[(d.month, d.day) for d in stripped_dates]}")
# After stripping, we should only get May 19 (from "19th")
assert any(d.month == 5 and d.day == 19 for d in stripped_dates), "19th should be found"
assert not any(d.month == 5 and d.day == 16 for d in stripped_dates), "05/16 from quote should NOT be found"
print("PASS  Quoted dates not extracted after stripping")

# ── Test 5: Full scenario — "What about 19th 4pm??" ──────────────────────

email_19th = Email(
    id="test-reply",
    sender="sus.aplham@proton.me",
    recipients=["modibhakt@elektrine.com"],
    subject="Re: You free?",
    body=reply_body,
    timestamp=datetime(2026, 5, 15, 19, 49, 49, tzinfo=timezone.utc),
)

events = [
    CalendarEvent(
        id="cal-003", title="Compliance Training Deadline",
        start=datetime(2026, 5, 15, 23, 59, tzinfo=timezone.utc),
        end=datetime(2026, 5, 15, 23, 59, tzinfo=timezone.utc),
        is_all_day=True, attendees=[],
    ),
    CalendarEvent(
        id="cal-007", title="Architecture Review",
        start=datetime(2026, 5, 16, 11, 0, tzinfo=timezone.utc),
        end=datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc),
        attendees=["you@company.com", "deepak.verma@company.com"],
    ),
    CalendarEvent(
        id="cal-008", title="Team Retrospective",
        start=datetime(2026, 5, 19, 16, 0, tzinfo=timezone.utc),
        end=datetime(2026, 5, 19, 17, 0, tzinfo=timezone.utc),
        attendees=["you@company.com", "team@company.com"],
        location="Zoom",
    ),
    CalendarEvent(
        id="cal-009", title="Hackathon Submission Deadline",
        start=datetime(2026, 5, 20, 18, 0, tzinfo=timezone.utc),
        end=datetime(2026, 5, 20, 18, 0, tzinfo=timezone.utc),
        is_all_day=True, attendees=[],
    ),
]

relevant = filter_relevant_events(email_19th, events)
relevant_ids = {e.id for e in relevant}
relevant_titles = [e.title for e in relevant]
print(f"  Relevant events for '19th 4pm': {relevant_titles}")

# MUST include Team Retrospective (May 19, 4-5pm) — date match on "19th"
assert "cal-008" in relevant_ids, f"Team Retrospective MUST match '19th': got {relevant_titles}"

# MUST NOT include Compliance Training (May 15) or Architecture Review (May 16)
# because those dates only appear in the quoted reply chain
assert "cal-003" not in relevant_ids, f"Compliance Training should NOT match: got {relevant_titles}"
assert "cal-007" not in relevant_ids, f"Architecture Review should NOT match: got {relevant_titles}"

print("PASS  Full scenario: '19th 4pm' matches Team Retrospective, NOT quoted-chain events")

# ── Test 6: Auto-event creation ───────────────────────────────────────────

cls = Classification(priority=Priority.NORMAL, category=Category.MEETING, confidence=0.8, reasoning="test")
auto_event = extract_meeting_event(email_19th, cls)
assert auto_event is not None, "Should create auto-event for meeting email"
assert auto_event.start.day == 19
assert auto_event.start.hour == 16  # 4pm
assert not auto_event.is_all_day
print(f"PASS  Auto-event created: {auto_event.title} at {auto_event.start}")

# ── Test 7: Casual email still gets no events and no auto-event ───────────

casual = Email(
    id="casual", sender="a@b.com", recipients=["c@d.com"],
    subject="yay", body="super secret pass meow Bye Khamar!",
    timestamp=datetime.now(timezone.utc),
)
r_casual = filter_relevant_events(casual, events)
assert len(r_casual) == 0, f"Casual email should get 0 events, got {len(r_casual)}"
cls_casual = Classification(priority=Priority.LOW, category=Category.INFO, confidence=0.9, reasoning="test")
auto_casual = extract_meeting_event(casual, cls_casual)
assert auto_casual is None, "Should NOT create auto-event for info email"
print("PASS  Casual email: 0 events, no auto-event")

print("\nAll 7 tests passed!")
