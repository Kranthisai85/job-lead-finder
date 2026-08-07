"""Outbound email transport (SMTP) — separate from queue business logic."""

from app.email.exceptions import (
    SmtpAuthenticationError,
    SmtpConnectionError,
    SmtpDisabledError,
    SmtpError,
    SmtpRecipientError,
    SmtpTimeoutError,
)
from app.email.message import build_email_message
from app.email.sender import EmailSender
from app.email.smtp_client import SmtpClient

__all__ = [
    "EmailSender",
    "SmtpAuthenticationError",
    "SmtpClient",
    "SmtpConnectionError",
    "SmtpDisabledError",
    "SmtpError",
    "SmtpRecipientError",
    "SmtpTimeoutError",
    "build_email_message",
]
