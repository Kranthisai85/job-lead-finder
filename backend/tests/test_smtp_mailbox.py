"""SMTP mailbox probe tests (no real network SMTP)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.contact_discovery.validators import is_outbound_safe_email
from app.email_queue.smtp_mailbox import SmtpMailboxConfig, SmtpMailboxValidator


def test_lists_local_part_is_not_outbound_safe() -> None:
    assert is_outbound_safe_email("lists@listtocart.com") is False
    assert is_outbound_safe_email("founder@acme.example") is True


@pytest.mark.asyncio
async def test_validate_many_maps_rcpt_codes() -> None:
    validator = SmtpMailboxValidator(
        SmtpMailboxConfig(
            sender="probe@acme.example",
            fail_open_on_transport_error=False,
            debug=True,
        )
    )

    replies = [
        b"220 mx.example.com ESMTP\r\n",
        b"250 OK\r\n",
        b"250 OK\r\n",
        b"250 OK\r\n",  # good@real.com
        b"550 No Such User Here\r\n",  # lists@real.com
        b"250 OK\r\n",  # RSET
        b"221 Bye\r\n",  # QUIT
    ]

    class FakeReader:
        def __init__(self) -> None:
            self._replies = list(replies)

        async def readline(self) -> bytes:
            if not self._replies:
                return b""
            return self._replies.pop(0)

    writer = MagicMock()
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()

    async def fake_open_connection(*_args, **_kwargs):
        return FakeReader(), writer

    async def fake_wait_for(awaitable, timeout=None):
        return await awaitable

    with (
        patch.object(
            validator,
            "resolve_mx_hosts",
            AsyncMock(return_value=["mx.example.com"]),
        ),
        patch("app.email_queue.smtp_mailbox.asyncio.open_connection", fake_open_connection),
        patch("app.email_queue.smtp_mailbox.asyncio.wait_for", fake_wait_for),
    ):
        results = await validator.validate_many(
            ["good@real.com", "lists@real.com"],
            sender="probe@acme.example",
        )

    assert results["good@real.com"] is True
    assert results["lists@real.com"] is False
    assert any("RCPT lists@real.com -> 550" in line for line in validator.last_transcript)


@pytest.mark.asyncio
async def test_transport_fail_open() -> None:
    validator = SmtpMailboxValidator(
        SmtpMailboxConfig(fail_open_on_transport_error=True, sender="a@b.com")
    )

    async def boom(*_args, **_kwargs):
        raise ConnectionRefusedError("blocked")

    async def fake_wait_for(awaitable, timeout=None):
        return await awaitable

    with (
        patch.object(validator, "resolve_mx_hosts", AsyncMock(return_value=["mx.example.com"])),
        patch("app.email_queue.smtp_mailbox.asyncio.open_connection", boom),
        patch("app.email_queue.smtp_mailbox.asyncio.wait_for", fake_wait_for),
    ):
        results = await validator.validate_many(["user@example.org"])

    assert results["user@example.org"] is True
