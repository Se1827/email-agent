"""Tests for the classifier service.

Uses monkeypatched LLM client so no real API calls are made.
"""

from __future__ import annotations

import json

import pytest

from src.models.email import Email, Priority, Category
from src.services.classifier import classify, _parse_classification


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_email() -> Email:
    return Email(
        id="test-001",
        sender="alice@example.com",
        recipients=["bob@example.com"],
        subject="Test Subject",
        body="Test body content",
        timestamp="2026-05-07T10:00:00+05:30",
    )


MOCK_CLASSIFICATION_JSON = json.dumps({
    "priority": "high",
    "category": "deadline",
    "confidence": 0.92,
    "reasoning": "The email mentions a deadline this Friday.",
})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestParseClassification:
    def test_plain_json(self):
        result = _parse_classification(MOCK_CLASSIFICATION_JSON)
        assert result.priority == Priority.HIGH
        assert result.category == Category.DEADLINE
        assert result.confidence == 0.92

    def test_json_wrapped_in_code_fence(self):
        wrapped = f"```json\n{MOCK_CLASSIFICATION_JSON}\n```"
        result = _parse_classification(wrapped)
        assert result.priority == Priority.HIGH

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            _parse_classification("not a json")


class TestClassify:
    @pytest.mark.asyncio
    async def test_classify_calls_llm(self, sample_email, monkeypatch):
        """Ensure classify() returns a valid Classification from a mocked LLM."""

        async def mock_chat(messages, **kwargs):
            return MOCK_CLASSIFICATION_JSON

        monkeypatch.setattr("src.services.classifier.llm.chat", mock_chat)

        classification, _ = await classify(sample_email)
        assert classification.priority == Priority.HIGH
        assert classification.category == Category.DEADLINE

    @pytest.mark.asyncio
    async def test_classify_masks_pii_before_llm(self, monkeypatch):
        email = Email(
            id="test-pii",
            sender="alice@example.com",
            recipients=["bob@example.com"],
            subject="Account question",
            body="My SSN is 123-45-6789 and my card is 4111-1111-1111-1111.",
            timestamp="2026-05-07T10:00:00+05:30",
        )
        captured = {}

        async def mock_chat(messages, **kwargs):
            captured["prompt"] = messages[-1]["content"]
            return MOCK_CLASSIFICATION_JSON

        monkeypatch.setattr("src.services.classifier.llm.chat", mock_chat)

        await classify(email)

        assert "123-45-6789" not in captured["prompt"]
        assert "4111-1111-1111-1111" not in captured["prompt"]
        assert "[[US_SSN_1]]" in captured["prompt"]
        assert "[[CREDIT_CARD_1]]" in captured["prompt"]
