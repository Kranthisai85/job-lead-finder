from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.core.config import settings
from app.core.logger import get_logger


class EmailTransport(Protocol):
    def send_message(self, message: EmailMessage) -> None: ...


class EmailSender:
    """SMTP email sender with dry-run support."""

    def __init__(
        self,
        *,
        transport: EmailTransport | None = None,
        dry_run: bool | None = None,
    ) -> None:
        self.transport = transport
        self.dry_run = settings.dry_run if dry_run is None else dry_run
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
                "email_dry_run to=%s name=%s subject=%s body_length=%d",
                recipient_email,
                recipient_name,
                subject,
                len(body),
            )
            return

        message = EmailMessage()
        message["From"] = settings.from_email
        message["Subject"] = subject
        if recipient_name:
            message["To"] = f"{recipient_name} <{recipient_email}>"
        else:
            message["To"] = recipient_email
        message.set_content(body)

        self.logger.info("email_send_started to=%s subject=%s", recipient_email, subject)
        await asyncio.to_thread(self._send_smtp, message)
        self.logger.info("email_send_completed to=%s subject=%s", recipient_email, subject)

    def _send_smtp(self, message: EmailMessage) -> None:
        if self.transport is not None:
            self.transport.send_message(message)
            return

        host = settings.smtp_host
        port = settings.smtp_port
        if not host:
            raise RuntimeError("SMTP_HOST is not configured")

        if settings.smtp_tls:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.starttls()
                if settings.smtp_username and settings.smtp_password:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                if settings.smtp_username and settings.smtp_password:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
