"""Provider-aware inbox identity normalization."""

from __future__ import annotations


def canonicalize_inbox(address: str | None, *, fallback: str = "mock") -> str:
    """Return a stable inbox identity without over-normalizing non-Gmail domains.

    Gmail treats dots and plus tags in the local part as aliases for consumer
    gmail.com/googlemail.com addresses. Other providers can treat those as
    distinct mailboxes, so we preserve dots and plus tags outside Gmail.
    """
    if not address:
        return fallback

    value = address.strip().lower()
    if "@" not in value:
        return value or fallback

    local, domain = value.rsplit("@", 1)
    if domain in {"gmail.com", "googlemail.com"}:
        local = local.split("+", 1)[0].replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"
