"""Build plain-text MIME messages from persisted queue drafts."""

from __future__ import annotations

from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import settings


def build_email_message(
    *,
    recipient_email: str,
    subject: str,
    body: str,
    recipient_name: str = "",
    from_email: str | None = None,
    from_name: str | None = None,
    reply_to: str | None = None,
) -> EmailMessage:
    """Construct a plain-text EmailMessage from an already-persisted draft."""
    sender_email = (
        from_email if from_email is not None else settings.effective_smtp_from_email
    ).strip()
    sender_name = (from_name if from_name is not None else (settings.smtp_from_name or "")).strip()
    if not sender_email:
        raise ValueError("SMTP_FROM_EMAIL is not configured")

    message = EmailMessage()
    if sender_name:
        message["From"] = formataddr((sender_name, sender_email))
    else:
        message["From"] = sender_email

    to_email = recipient_email.strip()
    if recipient_name and recipient_name.strip():
        message["To"] = formataddr((recipient_name.strip(), to_email))
    else:
        message["To"] = to_email

    message["Subject"] = subject
    configured_reply = reply_to if reply_to is not None else settings.smtp_reply_to
    if configured_reply and str(configured_reply).strip():
        message["Reply-To"] = str(configured_reply).strip()

    message.set_content(body or "")
    return message
