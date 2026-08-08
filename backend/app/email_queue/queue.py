from __future__ import annotations

from app.ai.types import GeneratedEmail
from app.sender_profile.types import SenderProfile, build_signature_block


def compose_email_body(
    email: GeneratedEmail,
    *,
    profile: SenderProfile | None = None,
) -> str:
    parts = [email.opening.strip(), email.body.strip(), email.cta.strip()]
    parts.append(build_signature_block(profile))
    return "\n\n".join(part for part in parts if part)
