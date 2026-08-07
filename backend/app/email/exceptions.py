"""Typed SMTP / outbound email errors (never include credentials)."""

from __future__ import annotations


class SmtpError(Exception):
    """Base SMTP delivery error with a safe, loggable message."""

    def __init__(self, message: str) -> None:
        self.safe_message = message
        super().__init__(message)


class SmtpDisabledError(SmtpError):
    """Raised when SMTP_ENABLED is false and dry-run is not active."""


class SmtpConnectionError(SmtpError):
    """Connection or TLS failure."""


class SmtpAuthenticationError(SmtpError):
    """SMTP login / authentication failure."""


class SmtpTimeoutError(SmtpError):
    """SMTP operation timed out."""


class SmtpRecipientError(SmtpError):
    """Recipient rejected or invalid for SMTP."""
