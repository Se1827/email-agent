"""Tests for the PII redaction module."""

from src.services.pii import redact


class TestCreditCard:
    def test_dashed_card_number(self):
        text = "My card is 4111-1111-1111-1111, please charge it."
        result = redact(text)
        assert "4111" not in result.text
        assert "credit_card" in result.found_types
        assert result.was_redacted

    def test_spaced_card_number(self):
        text = "Card: 5500 0000 0000 0004"
        result = redact(text)
        assert "5500" not in result.text
        assert result.was_redacted

    def test_plain_card_number(self):
        text = "Number: 4111111111111111"
        result = redact(text)
        assert "4111111111111111" not in result.text


class TestSSN:
    def test_standard_ssn(self):
        text = "SSN: 123-45-6789"
        result = redact(text)
        assert "123-45-6789" not in result.text
        assert "ssn" in result.found_types

    def test_no_false_positive_on_date(self):
        text = "Date: 2026-05-07"
        result = redact(text)
        assert "ssn" not in result.found_types


class TestBankAccount:
    def test_dashed_account(self):
        text = "Account: 9283-7461-0023"
        result = redact(text)
        assert "9283" not in result.text
        assert "bank_account" in result.found_types

    def test_routing_number(self):
        text = "Routing: 021000021"
        result = redact(text)
        assert "021000021" not in result.text
        assert "routing_number" in result.found_types


class TestNoRedaction:
    def test_clean_text(self):
        text = "Hello, this is a normal email about the project timeline."
        result = redact(text)
        assert result.text == text
        assert not result.was_redacted
        assert result.found_types == []
