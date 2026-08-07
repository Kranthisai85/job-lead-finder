"""Compatibility re-export — SMTP lives in app.email."""

from app.email.sender import EmailSender, EmailTransport

__all__ = ["EmailSender", "EmailTransport"]
