"""EmailSender — builds messages and delivers via SmtpClient (or injected transport)."""

from __future__ import annotations

import asyncio
from email.message import EmailMessage
from typing import Protocol

from app.core.config import settings
from app.core.logger import get_logger
from app.email.exceptions import SmtpDisabledError, SmtpError
from app.email.message import build_email_message
from app.email.smtp_client import SmtpClient, sanitize_smtp_error_message


class EmailTransport(Protocol):
    def send_message(self, message: EmailMessage) -> None: ...


class EmailSender:
    """Outbound transport wrapper with dry-run and SMTP_ENABLED gates."""

    def __init__(
        self,
        *,
        transport: EmailTransport | None = None,
        dry_run: bool | None = None,
        smtp_client: SmtpClient | None = None,
        smtp_enabled: bool | None = None,
    ) -> None:
        self.transport = transport
        self.smtp_client = smtp_client
        self.dry_run = settings.dry_run if dry_run is None else dry_run
        self.smtp_enabled = settings.smtp_enabled if smtp_enabled is None else smtp_enabled
        self.logger = get_logger(__name__)

    async def send(
        self,
        *,
        recipient_name: str,
        recipient_email: str,
        subject: str,
        body: str,
    ) -> None:
        if self.dry_run:
            self.logger.info(
                "[EMAIL] dry_run to=%s subject=%s body_length=%d",
                recipient_email,
                subject,
                len(body or ""),
            )
            return

        if not self.smtp_enabled and self.transport is None:
            raise SmtpDisabledError("SMTP is disabled")

        from_email = settings.effective_smtp_from_email
        if not from_email:
            if self.transport is not None:
                # Injected transports (tests) do not need production From config.
                from_email = "noreply@localhost"
            else:
                raise ValueError("SMTP_FROM_EMAIL is not configured")

        message = build_email_message(
            recipient_name=recipient_name,
            recipient_email=recipient_email,
            subject=subject,
            body=body,
            from_email=from_email,
        )

        self.logger.info("[EMAIL] smtp_send to=%s subject=%s", recipient_email, subject)
        try:
            await asyncio.to_thread(self._deliver, message)
        except SmtpError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise SmtpError(sanitize_smtp_error_message(exc)) from exc
        self.logger.info("[EMAIL] smtp_delivered to=%s", recipient_email)

    def _deliver(self, message: EmailMessage) -> None:
        if self.transport is not None:
            self.transport.send_message(message)
            return
        client = self.smtp_client or SmtpClient()
        client.send_message(message)
