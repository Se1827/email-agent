"""Multi-account manager — loads and resolves IMAP account configurations."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from src.models.email import AccountConfig

log = logging.getLogger(__name__)


def _stable_account_id(email: str) -> str:
    """Deterministic account ID from email address."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:12]


def load_accounts(data_dir: Path) -> list[AccountConfig]:
    """Load account configs from the accounts.json file.

    Falls back to a single default account built from IMAP env vars when
    the file does not exist.
    """
    accounts_file = data_dir / "accounts.json"
    if accounts_file.exists():
        try:
            with open(accounts_file) as f:
                raw = json.load(f)
            accounts = []
            for entry in raw:
                if not entry.get("id"):
                    entry["id"] = _stable_account_id(entry.get("email", ""))
                accounts.append(AccountConfig.model_validate(entry))
            log.info("accounts_loaded", extra={"count": len(accounts)})
            return accounts
        except Exception:
            log.exception("accounts_load_failed")

    return _default_account_from_env()


def _default_account_from_env() -> list[AccountConfig]:
    """Build a single account from the legacy IMAP environment variables."""
    import os
    source = os.getenv("EMAIL_SOURCE", "mock")
    if source == "mock":
        return [
            AccountConfig(
                id="mock-default",
                name="Demo Inbox",
                email="you@company.com",
                provider="mock",
                color="#3b82f6",
            )
        ]
    return [
        AccountConfig(
            id=_stable_account_id(os.getenv("IMAP_USER", "")),
            name="Primary",
            email=os.getenv("IMAP_USER", ""),
            provider="imap",
            imap_host=os.getenv("IMAP_HOST", ""),
            imap_port=int(os.getenv("IMAP_PORT", "993")),
            imap_user=os.getenv("IMAP_USER", ""),
            imap_pass=os.getenv("IMAP_PASS", ""),
            imap_mailbox=os.getenv("IMAP_MAILBOX", "INBOX"),
            imap_use_ssl=os.getenv("IMAP_USE_SSL", "true").lower() == "true",
            color="#3b82f6",
        )
    ]


def get_account(accounts: list[AccountConfig], account_id: str) -> AccountConfig | None:
    """Find an account by ID."""
    for account in accounts:
        if account.id == account_id:
            return account
    return None


def list_accounts_summary(accounts: list[AccountConfig]) -> list[dict[str, Any]]:
    """Return a sanitized list of accounts (no credentials)."""
    return [
        {
            "id": a.id,
            "name": a.name,
            "email": a.email,
            "provider": a.provider,
            "color": a.color,
            "is_active": a.is_active,
        }
        for a in accounts
    ]
