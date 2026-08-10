"""Lightweight deliverability checks before enqueue/send."""

from __future__ import annotations

import httpx

from app.core.logger import get_logger

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
