"""Tests for provider-aware inbox identity normalization."""

from src.services.inbox_identity import canonicalize_inbox
from src.storage import email_record_id


def test_gmail_dots_and_plus_tags_are_aliases():
    assert canonicalize_inbox("x.y+demo@gmail.com") == "xy@gmail.com"
    assert canonicalize_inbox("xy@googlemail.com") == "xy@gmail.com"


def test_non_gmail_dots_remain_distinct():
    assert canonicalize_inbox("x.y@example.com") == "x.y@example.com"
    assert canonicalize_inbox("xy@example.com") == "xy@example.com"
    assert canonicalize_inbox("x.y@example.com") != canonicalize_inbox("xy@example.com")


def test_storage_record_id_is_inbox_scoped():
    message_id = "provider-message-1"
    assert email_record_id(message_id, "a@example.com") != email_record_id(message_id, "b@example.com")
