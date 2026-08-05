from __future__ import annotations

from app.ai.types import GeneratedEmail


def compose_email_body(email: GeneratedEmail) -> str:
    parts = [email.opening.strip(), email.body.strip(), email.cta.strip()]
    signature = email.signature.strip()
    if signature and signature != "{{sender_name}}":
        parts.append(signature)
    elif signature:
        parts.append("Best regards,\n{{sender_name}}")
    return "\n\n".join(part for part in parts if part)
