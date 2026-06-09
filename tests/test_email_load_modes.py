"""Tests for DB-first inbox loading and source merge behavior."""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from src.api import routes
from src.models.email import Classification, Email
from src.models.email import AccountConfig, Classification, Email


def _email(
    email_id: str,
    *,
    body: str = "body",
    classification: Classification | None = None,
) -> Email:
    return Email(
        id=email_id,
        inbox="test@example.com",
        sender="sender@example.com",
        recipients=["test@example.com"],
        subject="Subject",
        body=body,
        timestamp="2026-05-15T10:00:00+00:00",
        classification=classification,
    )


def _classification() -> Classification:
    return Classification(
        priority="high",
        category="action-required",
        confidence=0.9,
        reasoning="Needs attention.",
    )


def _patch_loader_deps(monkeypatch, *, db_payloads, source_emails):
    routes._emails.clear()
    routes._calendar.clear()
    settings = SimpleNamespace(
        email_load_mode="db_then_source",
        email_source="imap",
        imap_user="test@example.com",
        imap_host="imap.example.com",
        imap_mailbox="INBOX",
        data_dir=Path("."),
    )
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    monkeypatch.setattr(routes, "load_email_states", lambda inbox=None: db_payloads)
    monkeypatch.setattr(routes, "_load_email_source", lambda: source_emails)
    monkeypatch.setattr(routes, "load_accounts", lambda path: [
        AccountConfig(
            id="mock-default",
            name="Demo Inbox",
            email="you@company.com",
            provider="mock",
            is_active=True,
        )
    ])
    monkeypatch.setattr(routes, "_load_account_email_source", lambda account, inbox: source_emails)
    monkeypatch.setattr(routes, "_store_email_memory", lambda email: None)
    monkeypatch.setattr(routes, "safe_store_email", lambda email, source: None)
    monkeypatch.setattr(routes, "safe_store_calendar_event", lambda event, source="mock": None)
    monkeypatch.setattr(routes, "load_events", lambda path: [])
    monkeypatch.setattr(routes, "safe_record_event", lambda *args, **kwargs: None)


def test_db_then_source_keeps_db_only_email_visible(monkeypatch):
    cached = _email("cached", classification=_classification())
    _patch_loader_deps(monkeypatch, db_payloads=[cached.model_dump(mode="json")], source_emails=[])

    routes._ensure_loaded()

    assert routes._emails["cached"].classification is not None
    assert routes._emails["cached"].storage_origin == "db"
    assert routes._emails["mock-default:cached"].classification is not None
    assert routes._emails["mock-default:cached"].storage_origin == "db"


def test_db_then_source_keeps_cached_state_for_unchanged_source_email(monkeypatch):
    cached = _email("same", body="unchanged", classification=_classification())
    fresh = _email("same", body="unchanged")
    _patch_loader_deps(monkeypatch, db_payloads=[cached.model_dump(mode="json")], source_emails=[fresh])

    routes._ensure_loaded()

    assert routes._emails["same"].classification == cached.classification
    assert routes._emails["same"].storage_origin == "source+cache"
    assert routes._emails["mock-default:same"].classification == cached.classification
    assert routes._emails["mock-default:same"].storage_origin == "source+cache"


def test_db_then_source_clears_cached_state_for_changed_source_email(monkeypatch):
    cached = _email("same", body="old", classification=_classification())
    fresh = _email("same", body="new")
    _patch_loader_deps(monkeypatch, db_payloads=[cached.model_dump(mode="json")], source_emails=[fresh])

    routes._ensure_loaded()

    assert routes._emails["same"].body == "new"
    assert routes._emails["same"].classification is None
    assert routes._emails["same"].storage_origin == "source-updated"
    assert routes._emails["mock-default:same"].body == "new"
    assert routes._emails["mock-default:same"].classification is None
    assert routes._emails["mock-default:same"].storage_origin == "source-updated"
