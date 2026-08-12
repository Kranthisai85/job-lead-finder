"""Lightweight deliverability checks before enqueue/send."""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logger import get_logger
from app.email_queue.smtp_mailbox import (
    SmtpMailboxConfig,
    SmtpMailboxValidator,
    helo_from_sender,
    sender_from_settings,
)

logger = get_logger(__name__)

_DNS_JSON_URL = "https://cloudflare-dns.com/dns-query"


async def domain_accepts_mail(domain: str, *, timeout: float = 5.0) -> bool:
    """True when the domain publishes MX records (mailbox may still not exist)."""
    host = (domain or "").strip().lower().rstrip(".")
    if not host or "." not in host:
        return False
    # RFC 2606 reserved names — used heavily in unit tests.
    if host.endswith((".example", ".test", ".invalid", ".localhost")):
        return True
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                _DNS_JSON_URL,
                params={"name": host, "type": "MX"},
                headers={"Accept": "application/dns-json"},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:  # noqa: BLE001 — fail open only on transport errors
        logger.warning("mx_lookup_failed domain=%s error=%s", host, exc)
        # If DNS lookup itself fails, do not block the whole pipeline.
        return True

    status = payload.get("Status")
    answers = payload.get("Answer") or []
    has_mx = any(int(item.get("type", 0)) == 15 for item in answers)
    if has_mx:
        return True
    # Status 0 = NOERROR; no MX usually means mail is not set up.
    if status == 0 and not has_mx:
        logger.info("mx_missing domain=%s", host)
        return False
    return False


def email_domain(email: str) -> str:
    if "@" not in (email or ""):
        return ""
    return email.rsplit("@", 1)[-1].strip().lower()


def build_mailbox_validator(*, debug: bool | None = None) -> SmtpMailboxValidator:
    sender = sender_from_settings(
        from_email=settings.smtp_from_email or settings.from_email or "",
        smtp_username=settings.smtp_username,
    )
    return SmtpMailboxValidator(
        SmtpMailboxConfig(
            smtp_port=settings.smtp_mailbox_verify_port,
            connect_timeout=settings.smtp_mailbox_verify_connect_timeout,
            read_timeout=settings.smtp_mailbox_verify_read_timeout,
            sender=sender,
            helo_hostname=helo_from_sender(sender),
            debug=settings.smtp_mailbox_verify_debug if debug is None else debug,
            fail_open_on_transport_error=settings.smtp_mailbox_verify_fail_open,
        )
    )


async def mailbox_accepts_address(email: str) -> bool:
    """True when SMTP RCPT TO accepts the mailbox (or check is disabled / fail-open)."""
    address = (email or "").strip().lower()
    if not address or "@" not in address:
        return False
    if not settings.smtp_mailbox_verify_enabled:
        return True
    domain = email_domain(address)
    if domain.endswith((".example", ".test", ".invalid", ".localhost")):
        return True
    validator = build_mailbox_validator()
    try:
        ok = await validator.validate(address)
    except Exception as exc:  # noqa: BLE001
        logger.warning("smtp_mailbox_check_error email=%s error=%s", address, exc)
        return bool(settings.smtp_mailbox_verify_fail_open)
    if not ok:
        logger.info("smtp_mailbox_rejected email=%s", address)
    return ok


async def validate_mailboxes(emails: list[str]) -> dict[str, bool]:
    """Batch SMTP mailbox check → {email: accepted}."""
    if not settings.smtp_mailbox_verify_enabled:
        return {email.strip().lower(): True for email in emails if email and "@" in email}
    validator = build_mailbox_validator()
    return await validator.validate_many(emails)
