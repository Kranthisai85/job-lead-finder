"""Sender profile types and signature helpers."""

from __future__ import annotations

from pydantic import BaseModel, Field

SENDER_NAME_PLACEHOLDER = "{{sender_name}}"


class SenderProfile(BaseModel):
    display_name: str = ""
    linkedin_url: str = ""
    github_url: str = ""


class SenderProfileUpdate(BaseModel):
    display_name: str = Field(default="", max_length=120)
    linkedin_url: str = Field(default="", max_length=500)
    github_url: str = Field(default="", max_length=500)


def build_signature_block(profile: SenderProfile | None) -> str:
    """Plain-text signature: name + optional LinkedIn/GitHub."""
    name = (profile.display_name if profile else "") or ""
    name = name.strip()
    lines = ["Best regards,"]
    lines.append(name if name else SENDER_NAME_PLACEHOLDER)
    if profile is not None:
        linkedin = (profile.linkedin_url or "").strip()
        github = (profile.github_url or "").strip()
        if linkedin:
            lines.append(f"LinkedIn: {linkedin}")
        if github:
            lines.append(f"GitHub: {github}")
    return "\n".join(lines)


def finalize_body_for_send(
    body: str,
    profile: SenderProfile | None,
    *,
    recipient_name: str = "",
) -> str:
    """Replace placeholders and expand signature using dashboard profile."""
    from app.email_queue.placeholders import scrub_template_placeholders

    text = body or ""
    signature = build_signature_block(profile)
    name = (profile.display_name if profile else "") or ""
    name = name.strip()

    text = scrub_template_placeholders(
        text,
        recipient_name=recipient_name,
        sender_name=name,
        keep_sender_placeholder=False,
    )

    if f"Best regards,\n{SENDER_NAME_PLACEHOLDER}" in text:
        text = text.replace(f"Best regards,\n{SENDER_NAME_PLACEHOLDER}", signature)
    if SENDER_NAME_PLACEHOLDER in text:
        text = text.replace(SENDER_NAME_PLACEHOLDER, name or "there")

    # If profile has links but body only has "Best regards,\nName", append links once.
    if profile is not None and name:
        linkedin = (profile.linkedin_url or "").strip()
        github = (profile.github_url or "").strip()
        simple_sig = f"Best regards,\n{name}"
        if text.rstrip().endswith(simple_sig) and (linkedin or github):
            text = text.rstrip()[: -len(simple_sig)] + signature
    return text
