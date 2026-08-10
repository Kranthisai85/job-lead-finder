from __future__ import annotations

from app.ai.types import GeneratedEmail
from app.sender_profile.types import SenderProfile, build_signature_block
from app.email_queue.placeholders import scrub_template_placeholders


def compose_email_body(
    email: GeneratedEmail,
    *,
    profile: SenderProfile | None = None,
    recipient_name: str = "",
) -> str:
    sender_name = (profile.display_name if profile else "") or ""
    parts = [email.opening.strip(), email.body.strip(), email.cta.strip()]
    parts.append(build_signature_block(profile))
    body = "\n\n".join(part for part in parts if part)
    return scrub_template_placeholders(
        body,
        recipient_name=recipient_name,
        sender_name=sender_name,
        keep_sender_placeholder=not bool(sender_name.strip()),
    )
