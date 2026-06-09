"""IMAP email connector — fetches real emails from an IMAP mailbox.

Works with any standard IMAP server (Gmail, Outlook, Yahoo, Fastmail,
self-hosted, etc.) — the same settings you would put into Thunderbird.
"""

from __future__ import annotations

import base64
import email
import email.header
import email.utils
import hashlib
import imaplib
import logging
from datetime import datetime, timezone
from email.message import Message

from src.models.email import Email
from src.models.email import Attachment, Email
from src.services import attachment as att_service

log = logging.getLogger(__name__)


def _decode_header(raw: str | None) -> str:
    """Decode an RFC 2047 encoded header into a plain string."""
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    decoded: list[str] = []
    for fragment, charset in parts:
        if isinstance(fragment, bytes):
            decoded.append(fragment.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(fragment)
    return " ".join(decoded)


def _extract_body(msg: Message) -> str:
    """Walk a MIME message and return the best plain-text body."""
    # Prefer text/plain, fall back to text/html stripped of tags.
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                continue
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        # No text/plain found, try text/html as a last resort.
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


def _parse_recipients(msg: Message) -> list[str]:
    """Extract all To/Cc addresses."""
    addrs: list[str] = []
    for header in ("To", "Cc"):
        raw = msg.get_all(header) or []
        for value in raw:
            parsed = email.utils.getaddresses([value])
            addrs.extend(addr for _, addr in parsed if addr)
    return addrs


def _parse_date(msg: Message) -> datetime:
    """Parse the Date header into a timezone-aware datetime."""
    raw = msg.get("Date", "")
    parsed = email.utils.parsedate_to_datetime(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _stable_id(msg_id: str | None, subject: str, date: str) -> str:
    """Generate a short stable ID from the Message-ID or a hash fallback."""
    raw = msg_id or f"{subject}-{date}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def fetch_emails(
    host: str,
    port: int,
    username: str,
    password: str,
    *,
    mailbox: str = "INBOX",
    limit: int = 20,
    use_ssl: bool = True,
    inbox: str | None = None,
) -> list[Email]:
    """Connect to an IMAP server and fetch the latest emails.

    Parameters mirror what you would enter in any email client:
      - host:     IMAP server (e.g. imap.gmail.com)
      - port:     usually 993 for SSL
      - username: your email address
      - password: your password or app-specific password
      - mailbox:  folder to read from (default INBOX)
      - limit:    how many recent emails to fetch
      - use_ssl:  whether to use SSL (default True)
    """
    klass = imaplib.IMAP4_SSL if use_ssl else imaplib.IMAP4
    log.info("imap_connect", extra={"host": host, "user": username})

    conn = klass(host, port)
    try:
        conn.login(username, password)
        conn.select(mailbox, readonly=True)

        # Search for all messages, take the latest `limit`.
        _status, data = conn.search(None, "ALL")
        msg_nums = data[0].split()
        if not msg_nums:
            log.info("imap_empty", extra={"mailbox": mailbox})
            return []

        # Most recent first.
        msg_nums = msg_nums[-limit:]
        msg_nums.reverse()

        emails: list[Email] = []
        for num in msg_nums:
            _status, msg_data = conn.fetch(num, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            raw_bytes = msg_data[0][1]
            msg = email.message_from_bytes(raw_bytes)

            sender_pairs = email.utils.getaddresses([msg.get("From", "")])
            sender = sender_pairs[0][1] if sender_pairs else "unknown"

            subject = _decode_header(msg.get("Subject"))
            date = _parse_date(msg)
            body = _extract_body(msg)
            recipients = _parse_recipients(msg)
            msg_id = msg.get("Message-ID")
            thread_id = msg.get("In-Reply-To") or msg.get("References", "").split()[0] if msg.get("References") else None

            attachments = []
            if msg.is_multipart():
                for part in msg.walk():
                    disposition = str(part.get("Content-Disposition", ""))
                    filename_raw = part.get_filename()
                    if "attachment" in disposition or filename_raw:
                        filename = _decode_header(filename_raw or "unnamed_attachment")
                        content_type = part.get_content_type()
                        payload = part.get_payload(decode=True)
                        if payload is not None:
                            b64_content = base64.b64encode(payload).decode("utf-8")
                            is_safe, scan_results = att_service.scan_security(filename, payload)
                            text_content = None
                            pii_detected = []
                            if is_safe:
                                text_content = att_service.extract_text(payload, content_type, filename)
                                if text_content:
                                    pii_detected = att_service.detect_pii(text_content)
                            
                            attachments.append(Attachment(
                                filename=filename,
                                content_type=content_type,
                                size_bytes=len(payload),
                                content=b64_content,
                                text_content=text_content,
                                is_safe=is_safe,
                                scan_results=scan_results,
                                pii_detected=pii_detected,
                            ))

            emails.append(Email(
                id=_stable_id(msg_id, subject, str(date)),
                inbox=inbox,
                sender=sender,
                recipients=recipients,
                subject=subject,
                body=body[:5000],  # cap very long emails
                timestamp=date,
                thread_id=thread_id,
                attachments=attachments,
            ))

        log.info("imap_fetched", extra={"count": len(emails)})
        return emails

    finally:
        try:
            conn.logout()
        except Exception:
            pass
