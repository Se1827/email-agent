"""Multi-account manager — loads and resolves IMAP account configurations."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.models.email import AccountConfig
from src.services.inbox_identity import canonicalize_inbox

log = logging.getLogger(__name__)


def _stable_account_id(email: str) -> str:
    """Deterministic account ID from email address."""
    normalized = email.strip().lower()
    if not normalized:
        return f"account-{uuid4().hex[:8]}"
    return hashlib.sha256(normalized.encode()).hexdigest()[:12]


def account_inbox(account: AccountConfig) -> str:
    """Return the storage inbox scope for an account."""
    fallback = f"{account.provider}:{account.id}:{account.imap_mailbox}"
    return canonicalize_inbox(account.email or account.imap_user, fallback=fallback)


def load_accounts(data_dir: Path) -> list[AccountConfig]:
    """Load account configs from the accounts.json file.

    Initialises accounts.json with dummy data when the file does not exist.
    """
    accounts_file = data_dir / "accounts.json"
    
    if not accounts_file.exists():
        dummy_account = AccountConfig(
            id="testing",
            name="Se1827",
            email="se1827@mock.com",
            provider="mock",
            imap_host="",
            imap_port=993,
            imap_user="se1827@mock.com",
            imap_pass="",
            imap_mailbox="INBOX",
            imap_use_ssl=True,
            color="#3b82f6",
            is_active=True
        )
        try:
            save_accounts(data_dir, [dummy_account])
            log.info("accounts_file_initialized_with_dummy_data")
        except Exception:
            log.exception("accounts_initialization_failed")

    if accounts_file.exists():
        try:
            with open(accounts_file, encoding="utf-8") as f:
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


def save_accounts(data_dir: Path, accounts: list[AccountConfig]) -> None:
    """Persist account configs to accounts.json."""
    accounts_file = data_dir / "accounts.json"
    accounts_file.parent.mkdir(parents=True, exist_ok=True)
    payload = [account.model_dump(mode="json") for account in accounts]
    with open(accounts_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4)
        f.write("\n")


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
    if source == "graph":
        return [
            AccountConfig(
                id="graph-default",
                name="Microsoft 365",
                email=os.getenv("GRAPH_USER_EMAIL", "se1827@outlook.com"),
                provider="graph",
                color="#6366f1",
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
            "imap_host": a.imap_host,
            "imap_port": a.imap_port,
            "imap_user": a.imap_user,
            "imap_mailbox": a.imap_mailbox,
            "imap_use_ssl": a.imap_use_ssl,
            "smtp_host": a.smtp_host,
            "smtp_port": a.smtp_port,
            "smtp_user": a.smtp_user or a.imap_user or a.email,
            "smtp_use_ssl": a.smtp_use_ssl,
            "smtp_use_tls": a.smtp_use_tls,
            "has_smtp": bool(a.smtp_host),
            "color": a.color,
            "is_active": a.is_active,
            "has_password": bool(a.imap_pass),
        }
        for a in accounts
    ]


def resolve_smtp_settings(account: AccountConfig) -> dict[str, Any]:
    """Resolve SMTP connection settings from account config.

    Fallback chain: account SMTP fields → account IMAP creds → env defaults.
    """
    from src.config import get_settings

    cfg = get_settings()

    host = account.smtp_host or cfg.smtp_host or account.imap_host or cfg.imap_host
    port = account.smtp_port if account.smtp_host else (cfg.smtp_port or 587)
    user = (
        account.smtp_user
        or account.imap_user
        or account.email
        or cfg.smtp_user
        or cfg.imap_user
    )
    password = (
        account.smtp_pass
        or account.imap_pass
        or cfg.smtp_pass
        or cfg.imap_pass
    )
    use_ssl = account.smtp_use_ssl if account.smtp_host else cfg.smtp_use_ssl
    use_tls = account.smtp_use_tls if account.smtp_host else cfg.smtp_use_tls
    from_addr = account.email or user
    from_name = account.name or ""

    if not host:
        raise RuntimeError(
            f"No SMTP host configured for account '{account.name}'. "
            "Set smtp_host in the account or SMTP_HOST in .env."
        )
    if not password:
        raise RuntimeError(
            f"No SMTP password configured for account '{account.name}'. "
            "Set smtp_pass in the account or SMTP_PASS in .env."
        )

    return {
        "host": host,
        "port": port,
        "username": user,
        "password": password,
        "use_ssl": use_ssl,
        "use_tls": use_tls,
        "from_addr": from_addr,
        "from_name": from_name,
    }
