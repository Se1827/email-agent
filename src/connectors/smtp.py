"""SMTP email connector — sends real emails via SMTP.

Works with any standard SMTP server (Gmail, Outlook, Yahoo, Fastmail,
self-hosted, etc.) — the same settings you would put into Thunderbird.
"""

from __future__ import annotations

import logging
import smtplib
import socket
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid

log = logging.getLogger(__name__)


def _generate_message_id(domain: str = "emailagent.local") -> str:
    """Generate a globally-unique RFC-2822 Message-ID."""
    return make_msgid(domain=domain)


def _normalize_subject_for_reply(subject: str) -> str:
    """Ensure the subject starts with 'Re:' for replies."""
    stripped = subject.strip()
    if stripped.lower().startswith("re:"):
        return stripped
    return f"Re: {stripped}"


def send_email(
    host: str,
    port: int,
    username: str,
    password: str,
    *,
    use_ssl: bool = False,
    use_tls: bool = True,
    from_addr: str,
    from_name: str = "",
    to_addrs: list[str],
    cc_addrs: list[str] | None = None,
    subject: str,
    body: str,
    in_reply_to: str | None = None,
    references: list[str] | None = None,
    message_id: str | None = None,
) -> str:
    """Send an email via SMTP and return the generated Message-ID.

    Parameters mirror what you would enter in any email client:
      - host:       SMTP server (e.g. smtp.gmail.com)
      - port:       usually 587 for STARTTLS, 465 for SSL
      - username:   your email address or login
      - password:   your password or app-specific password
      - use_ssl:    True for direct SSL connection (port 465)
      - use_tls:    True for STARTTLS upgrade (port 587)
      - from_addr:  sender email address
      - from_name:  sender display name (optional)
      - to_addrs:   list of recipient email addresses
      - cc_addrs:   list of CC email addresses (optional)
      - subject:    email subject
      - body:       plain-text email body
      - in_reply_to: Message-ID of the email being replied to
      - references:  list of Message-IDs forming the thread chain
      - message_id:  pre-generated Message-ID (generated if omitted)
    """
    cc_addrs = cc_addrs or []

    # Extract domain from sender address for Message-ID generation
    domain = from_addr.split("@")[1] if "@" in from_addr else "emailagent.local"
    msg_id = message_id or _generate_message_id(domain)

    # Build MIME message
    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr((from_name, from_addr)) if from_name else from_addr
    msg["To"] = ", ".join(to_addrs)
    if cc_addrs:
        msg["Cc"] = ", ".join(cc_addrs)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = msg_id

    # Threading headers (RFC-2822 §3.6.4)
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = " ".join(references)

    # Attach plain-text body
    msg.attach(MIMEText(body, "plain", "utf-8"))

    # All recipients (To + Cc)
    all_recipients = list(to_addrs) + list(cc_addrs)

    log.info(
        "smtp_sending",
        extra={
            "host": host,
            "port": port,
            "from": from_addr,
            "to_count": len(to_addrs),
            "cc_count": len(cc_addrs),
            "has_reply_to": bool(in_reply_to),
        },
    )

    try:
        if use_ssl:
            # Direct SSL (typically port 465)
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()

        try:
            server.login(username, password)
            server.sendmail(from_addr, all_recipients, msg.as_string())
            log.info("smtp_sent", extra={"message_id": msg_id})
        finally:
            try:
                server.quit()
            except Exception:
                pass

    except smtplib.SMTPAuthenticationError as exc:
        log.error("smtp_auth_failed", extra={"host": host, "user": username, "error": str(exc)})
        raise RuntimeError(
            f"SMTP authentication failed for {username}@{host}. "
            "Check your SMTP username and password (use an app-specific password for Gmail)."
        ) from exc
    except (smtplib.SMTPException, socket.error) as exc:
        log.error("smtp_send_failed", extra={"host": host, "error": str(exc)})
        raise RuntimeError(f"SMTP send failed: {exc}") from exc

    return msg_id
