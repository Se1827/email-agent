"""Tests for the drafter service.

Uses monkeypatched LLM client so no real API calls are made.
"""

from __future__ import annotations

import pytest

from src.models.email import Classification, Email, Priority, Category
from src.services.drafter import draft_reply


@pytest.fixture()
def sample_email() -> Email:
    return Email(
        id="test-002",
        sender="alice@example.com",
        recipients=["bob@example.com"],
        subject="OKR deadline Friday",
        body="Please submit your OKR self-assessment by Thursday EOD.",
        timestamp="2026-05-07T10:00:00+05:30",
    )


@pytest.fixture()
def sample_classification() -> Classification:
    return Classification(
        priority=Priority.HIGH,
        category=Category.DEADLINE,
        confidence=0.9,
        reasoning="OKR deadline.",
    )


MOCK_REPLY = "Thanks for the reminder. I will have my self-assessment submitted by Thursday EOD."


class TestDraftReply:
    @pytest.mark.asyncio
    async def test_draft_returns_reply(self, sample_email, sample_classification, monkeypatch):
        async def mock_chat(messages, **kwargs):
            return MOCK_REPLY

        monkeypatch.setattr("src.services.drafter.llm.chat", mock_chat)

        result = await draft_reply(sample_email, sample_classification)
        assert result.body == MOCK_REPLY
        assert result.pii_redacted is False

    @pytest.mark.asyncio
    async def test_draft_redacts_pii(self, sample_email, sample_classification, monkeypatch):
        reply_with_pii = "Sure, my SSN is 123-45-6789 and card is 4111-1111-1111-1111."

        async def mock_chat(messages, **kwargs):
            return reply_with_pii

        monkeypatch.setattr("src.services.drafter.llm.chat", mock_chat)

        result = await draft_reply(sample_email, sample_classification)
        assert "123-45-6789" not in result.body
        assert result.pii_redacted is True
        assert "ssn" in result.redacted_types

    @pytest.mark.asyncio
    async def test_draft_masks_prompt_and_rehydrates_known_values(
        self, sample_classification, monkeypatch
    ):
        email = Email(
            id="test-003",
            sender="alice@example.com",
            recipients=["bob@example.com"],
            subject="Payment help",
            body="Please confirm card 4111-1111-1111-1111 was removed.",
            timestamp="2026-05-07T10:00:00+05:30",
        )
        captured = {}

        async def mock_chat(messages, **kwargs):
            captured["prompt"] = messages[-1]["content"]
            return "I confirm that [[CREDIT_CARD_1]] was removed from the account."

        monkeypatch.setattr("src.services.drafter.llm.chat", mock_chat)

        result = await draft_reply(email, sample_classification)

        assert "4111-1111-1111-1111" not in captured["prompt"]
        assert "[[CREDIT_CARD_1]]" in captured["prompt"]
        assert "4111-1111-1111-1111" in result.body
        assert "[[CREDIT_CARD_1]]" not in result.body
