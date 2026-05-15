"""Quick test for the smart calendar relevance filter."""
from datetime import datetime, timezone
from src.models.email import Email, CalendarEvent
from src.services.classifier import filter_relevant_events

# Test 1: Casual email with no time references → NO events
casual = Email(
    id="t1", sender="a@b.com", recipients=["c@d.com"],
    subject="yay",
    body="super secret pass: 1231@@1kjlqs..asdoiq2oi\nmeow\nBye Khamar!",
    timestamp=datetime.now(timezone.utc),
)
events = [
    CalendarEvent(
        title="Compliance Training Deadline",
        start=datetime.now(timezone.utc),
        end=datetime.now(timezone.utc),
        attendees=["x@y.com"],
    )
]
r1 = filter_relevant_events(casual, events)
assert len(r1) == 0, f"Expected 0 relevant events for casual email, got {len(r1)}"
print("PASS  Test 1: Casual email gets 0 calendar events")

# Test 2: Email mentioning meeting from a matching attendee → 1 event
meeting_email = Email(
    id="t2", sender="raj.patel@company.com", recipients=["you@company.com"],
    subject="About tomorrow's meeting",
    body="Can we discuss the sprint planning session?",
    timestamp=datetime.now(timezone.utc),
)
events2 = [
    CalendarEvent(
        title="Sprint Planning",
        start=datetime.now(timezone.utc),
        end=datetime.now(timezone.utc),
        attendees=["you@company.com", "raj.patel@company.com"],
    ),
    CalendarEvent(
        title="Unrelated Event",
        start=datetime.now(timezone.utc),
        end=datetime.now(timezone.utc),
        attendees=["someone@else.com"],
    ),
]
r2 = filter_relevant_events(meeting_email, events2)
assert len(r2) == 1, f"Expected 1 relevant event, got {len(r2)}"
assert r2[0].title == "Sprint Planning"
print("PASS  Test 2: Meeting email matches attendee-overlap event only")

# Test 3: Email about OKR with keyword match → 1 event
deadline_email = Email(
    id="t3", sender="boss@company.com", recipients=["you@company.com"],
    subject="OKR Review Submission",
    body="Please submit your OKR review by tomorrow deadline.",
    timestamp=datetime.now(timezone.utc),
)
events3 = [
    CalendarEvent(
        title="OKR Review Submission",
        start=datetime.now(timezone.utc),
        end=datetime.now(timezone.utc),
        attendees=[],
    ),
    CalendarEvent(
        title="Random Team Lunch",
        start=datetime.now(timezone.utc),
        end=datetime.now(timezone.utc),
        attendees=[],
    ),
]
r3 = filter_relevant_events(deadline_email, events3)
assert len(r3) == 1, f"Expected 1 relevant event, got {len(r3)}"
assert r3[0].title == "OKR Review Submission"
print("PASS  Test 3: Keyword-match deadline email gets correct event")

# Test 4: Email with no time words at all → always empty
no_time = Email(
    id="t4", sender="newsletter@spam.com", recipients=["you@company.com"],
    subject="Weekly digest",
    body="Here are some interesting articles for you this week.",
    timestamp=datetime.now(timezone.utc),
)
r4 = filter_relevant_events(no_time, events3)
assert len(r4) == 0, f"Expected 0 events for non-time email, got {len(r4)}"
print("PASS  Test 4: Newsletter with no time refs gets 0 events")

print("\nAll 4 relevance filter tests passed!")
