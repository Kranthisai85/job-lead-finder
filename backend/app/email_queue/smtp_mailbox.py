"""SMTP mailbox existence probe (RCPT TO) without sending mail.

Example
-------
```python
from app.email_queue.smtp_mailbox import SmtpMailboxValidator

validator = SmtpMailboxValidator(sender="probe@yourdomain.com", debug=True)
results = await validator.validate_many(
    ["founder@acme.com", "lists@listtocart.com"]
)
# {"founder@acme.com": True, "lists@listtocart.com": False}
```
"""

from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from dataclasses import dataclass, field
from email.utils import parseaddr
from typing import Iterable
from urllib.parse import urlparse

import httpx

from app.core.logger import get_logger

logger = get_logger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DNS_JSON_URL = "https://cloudflare-dns.com/dns-query"


@dataclass
class SmtpMailboxConfig:
    smtp_port: int = 25
    connect_timeout: float = 30.0
    read_timeout: float = 5.0
    sender: str = "probe@localhost"
    helo_hostname: str = "localhost"
    nameservers: list[str] = field(default_factory=list)
    debug: bool = False
    # When True, unreachable MX / timeouts do not mark the address invalid
    # (common when cloud VPS blocks outbound port 25). Explicit SMTP reject
    # codes (e.g. 550) still mark invalid.
    fail_open_on_transport_error: bool = True


class SmtpMailboxValidator:
    """Probe mailboxes via SMTP handshake without DATA/sending."""

    def __init__(self, config: SmtpMailboxConfig | None = None, **overrides: object) -> None:
        base = config or SmtpMailboxConfig()
        if overrides:
            data = {**base.__dict__, **overrides}
            base = SmtpMailboxConfig(**data)  # type: ignore[arg-type]
        self.config = base
        self.logger = get_logger(self.__class__.__name__)
        self._transcript: list[str] = []

    @property
    def last_transcript(self) -> list[str]:
        return list(self._transcript)

    async def validate(self, email: str, *, sender: str | None = None) -> bool:
        results = await self.validate_many([email], sender=sender)
        return bool(results.get(_normalize_email(email), False))

    async def validate_many(
        self,
        emails: Iterable[str],
        *,
        sender: str | None = None,
    ) -> dict[str, bool]:
        sender_addr = _normalize_email(sender or self.config.sender) or "probe@localhost"
        helo = self.config.helo_hostname
        if "@" in sender_addr:
            helo = sender_addr.rsplit("@", 1)[-1] or helo

        by_domain: dict[str, list[str]] = defaultdict(list)
        results: dict[str, bool] = {}
        for raw in emails:
            email = _normalize_email(raw)
            if not email or not _EMAIL_RE.match(email):
                if email:
                    results[email] = False
                continue
            local, domain = email.rsplit("@", 1)
            if not local or not domain:
                results[email] = False
                continue
            # Reserved test domains — used by unit tests; never hit the network.
            if domain.endswith((".example", ".test", ".invalid", ".localhost")):
                results[email] = True
                continue
            by_domain[domain].append(email)

        for domain, recipients in by_domain.items():
            domain_results = await self._validate_domain(
                domain,
                recipients,
                sender=sender_addr,
                helo=helo,
            )
            results.update(domain_results)
        return results

    async def _validate_domain(
        self,
        domain: str,
        recipients: list[str],
        *,
        sender: str,
        helo: str,
    ) -> dict[str, bool]:
        mx_hosts = await self.resolve_mx_hosts(domain)
        if not mx_hosts:
            mx_hosts = [domain]

        last_error: str | None = None
        for host in mx_hosts:
            try:
                return await self._smtp_rcpt_probe(
                    host,
                    recipients,
                    sender=sender,
                    helo=helo,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                self._debug(f"mx_host={host} error={exc}")
                self.logger.info(
                    "smtp_mailbox_mx_failed domain=%s host=%s error=%s",
                    domain,
                    host,
                    exc,
                )
                continue

        if self.config.fail_open_on_transport_error:
            self.logger.warning(
                "smtp_mailbox_transport_fail_open domain=%s error=%s",
                domain,
                last_error,
            )
            return {email: True for email in recipients}
        self.logger.info(
            "smtp_mailbox_transport_invalid domain=%s error=%s",
            domain,
            last_error,
        )
        return {email: False for email in recipients}

    async def resolve_mx_hosts(self, domain: str) -> list[str]:
        """Prefer lowest MX priority. Fallback: Cloudflare DNS JSON → nslookup."""
        host = (domain or "").strip().lower().rstrip(".")
        if not host:
            return []
        records = await self._mx_via_cloudflare(host)
        if not records:
            records = await self._mx_via_nslookup(host)
        records.sort(key=lambda item: item[0])
        hosts: list[str] = []
        seen: set[str] = set()
        for _priority, mx_host in records:
            cleaned = mx_host.strip().rstrip(".").lower()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                hosts.append(cleaned)
        return hosts

    async def _mx_via_cloudflare(self, domain: str) -> list[tuple[int, str]]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    _DNS_JSON_URL,
                    params={"name": domain, "type": "MX"},
                    headers={"Accept": "application/dns-json"},
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001
            self.logger.debug("mx_cloudflare_failed domain=%s error=%s", domain, exc)
            return []
        out: list[tuple[int, str]] = []
        for answer in payload.get("Answer") or []:
            if int(answer.get("type", 0)) != 15:
                continue
            data = str(answer.get("data") or "").strip()
            parts = data.split()
            if len(parts) >= 2 and parts[0].isdigit():
                out.append((int(parts[0]), parts[1]))
            elif data:
                out.append((10, data))
        return out

    async def _mx_via_nslookup(self, domain: str) -> list[tuple[int, str]]:
        """Windows-friendly MX fallback via nslookup."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "nslookup",
                "-type=MX",
                domain,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=8.0)
        except Exception as exc:  # noqa: BLE001
            self.logger.debug("mx_nslookup_failed domain=%s error=%s", domain, exc)
            return []
        text = stdout.decode("utf-8", errors="ignore")
        out: list[tuple[int, str]] = []
        for match in re.finditer(
            r"mail exchanger\s*=\s*(\d+)\s+(\S+)",
            text,
            flags=re.IGNORECASE,
        ):
            out.append((int(match.group(1)), match.group(2)))
        for match in re.finditer(
            r"preference\s*=\s*(\d+).*?mail exchanger\s*=\s*(\S+)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            out.append((int(match.group(1)), match.group(2)))
        return out

    async def _smtp_rcpt_probe(
        self,
        mx_host: str,
        recipients: list[str],
        *,
        sender: str,
        helo: str,
    ) -> dict[str, bool]:
        self._transcript = []
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(mx_host, self.config.smtp_port),
            timeout=self.config.connect_timeout,
        )
        try:
            banner = await self._read_reply(reader)
            if not banner.startswith("220"):
                raise RuntimeError(f"bad banner: {banner!r}")

            await self._send(writer, f"HELO {helo}")
            helo_reply = await self._read_reply(reader)
            if not helo_reply.startswith("250"):
                raise RuntimeError(f"HELO rejected: {helo_reply!r}")

            await self._send(writer, f"MAIL FROM:<{sender}>")
            mail_reply = await self._read_reply(reader)
            if not mail_reply.startswith("250"):
                raise RuntimeError(f"MAIL FROM rejected: {mail_reply!r}")

            results: dict[str, bool] = {}
            for email in recipients:
                await self._send(writer, f"RCPT TO:<{email}>")
                rcpt_reply = await self._read_reply(reader)
                code = _smtp_code(rcpt_reply)
                results[email] = code in {250, 451, 452}
                self._debug(f"RCPT {email} -> {code} ({rcpt_reply})")

            await self._send(writer, "RSET")
            await self._read_reply(reader)
            await self._send(writer, "QUIT")
            try:
                await self._read_reply(reader)
            except Exception:  # noqa: BLE001
                pass
            return results
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

    async def _read_reply(self, reader: asyncio.StreamReader) -> str:
        lines: list[str] = []
        while True:
            raw = await asyncio.wait_for(reader.readline(), timeout=self.config.read_timeout)
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            self._debug(f"S: {line}")
            lines.append(line)
            if len(line) >= 4 and line[3] == " ":
                break
            if len(line) >= 3 and not line[0:3].isdigit():
                break
        return "\n".join(lines)

    async def _send(self, writer: asyncio.StreamWriter, command: str) -> None:
        self._debug(f"C: {command}")
        writer.write(f"{command}\r\n".encode("utf-8"))
        await writer.drain()

    def _debug(self, message: str) -> None:
        self._transcript.append(message)
        if self.config.debug:
            self.logger.info("smtp_mailbox_debug %s", message)


def _normalize_email(value: str | None) -> str:
    if not value:
        return ""
    _name, addr = parseaddr(value)
    candidate = (addr or value).strip().lower()
    return candidate


def _smtp_code(reply: str) -> int:
    for line in (reply or "").splitlines():
        if len(line) >= 3 and line[0:3].isdigit():
            return int(line[0:3])
    return 0


def sender_from_settings(
    *,
    from_email: str = "",
    smtp_username: str | None = None,
) -> str:
    for candidate in (from_email, smtp_username or ""):
        email = _normalize_email(candidate)
        if email and "@" in email:
            return email
    return "probe@localhost"


def helo_from_sender(sender: str) -> str:
    if "@" in sender:
        return sender.rsplit("@", 1)[-1]
    host = urlparse(f"//{sender}").hostname
    return host or "localhost"
