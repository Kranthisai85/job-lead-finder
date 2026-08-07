"""stdlib smtplib transport — no queue state transitions."""

from __future__ import annotations

import smtplib
import socket
from email.message import EmailMessage
from typing import Any

from app.core.config import settings
from app.core.logger import get_logger
from app.email.exceptions import (
    SmtpAuthenticationError,
    SmtpConnectionError,
    SmtpError,
    SmtpRecipientError,
    SmtpTimeoutError,
)

logger = get_logger(__name__)


def sanitize_smtp_error_message(exc: BaseException) -> str:
    """Return a concise error string that never includes SMTP credentials."""
    text = str(exc) or exc.__class__.__name__
    password = settings.smtp_password
    if password:
        text = text.replace(password, "***")
    username = settings.smtp_username
    if username and len(username) > 2:
        text = text.replace(username, "***")
    # Collapse noisy multi-line SMTP responses.
    text = " ".join(text.split())
    if len(text) > 240:
        text = text[:237] + "..."
    return text


class SmtpClient:
    """Establish SMTP, optionally STARTTLS + auth, send one message, close."""

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.host = settings.smtp_host if host is None else host
        self.port = settings.smtp_port if port is None else port
        self.username = settings.smtp_username if username is None else username
        self.password = settings.smtp_password if password is None else password
        self.use_tls = settings.effective_smtp_use_tls if use_tls is None else use_tls
        self.timeout_seconds = (
            settings.smtp_timeout_seconds if timeout_seconds is None else timeout_seconds
        )

    def send_message(self, message: EmailMessage) -> None:
        if not self.host:
            raise SmtpConnectionError("SMTP_HOST is not configured")

        smtp: smtplib.SMTP | None = None
        try:
            smtp = smtplib.SMTP(
                self.host,
                self.port,
                timeout=self.timeout_seconds,
            )
            if self.use_tls:
                smtp.starttls()
            if self.username and self.password:
                smtp.login(self.username, self.password)
            smtp.send_message(message)
        except smtplib.SMTPAuthenticationError as exc:
            raise SmtpAuthenticationError("SMTP authentication failed") from exc
        except smtplib.SMTPRecipientsRefused as exc:
            raise SmtpRecipientError("SMTP recipient rejected") from exc
        except smtplib.SMTPSenderRefused as exc:
            raise SmtpRecipientError("SMTP sender rejected") from exc
        except smtplib.SMTPDataError as exc:
            raise SmtpError("SMTP server rejected message") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise SmtpTimeoutError("SMTP connection timed out") from exc
        except (smtplib.SMTPConnectError, ConnectionError, OSError) as exc:
            raise SmtpConnectionError(
                f"SMTP connection failed: {sanitize_smtp_error_message(exc)}"
            ) from exc
        except smtplib.SMTPException as exc:
            raise SmtpError(f"SMTP error: {sanitize_smtp_error_message(exc)}") from exc
        finally:
            if smtp is not None:
                try:
                    smtp.quit()
                except Exception:  # noqa: BLE001 — best-effort close
                    try:
                        smtp.close()
                    except Exception:  # noqa: BLE001
                        pass

    def send(self, message: EmailMessage) -> None:
        """Alias used by tests / Protocol compatibility."""
        self.send_message(message)


class InjectableTransport:
    """Adapter so call sites can inject a mock with send_message()."""

    def __init__(self, transport: Any) -> None:
        self._transport = transport

    def send_message(self, message: EmailMessage) -> None:
        self._transport.send_message(message)
