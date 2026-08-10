"""Strip leftover LLM template placeholders from outbound email text."""

from __future__ import annotations

import re

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
_EMPTY_GREETING_RE = re.compile(
    r"(?im)^(?:hi|hello|hey)\s*,\s*(?:\n|$)"
)
_GENERIC_NAMES = frozenset({"there", "unknown", "team", "friend", "sir", "madam"})


def resolve_first_name(recipient_name: str | None) -> str:
    name = re.sub(r"\s+", " ", (recipient_name or "").strip())
    if not name or name.lower() in _GENERIC_NAMES:
        return ""
    # Avoid using company slogans / polluted titles as a greeting name.
    if ":" in name or "—" in name or len(name) > 40:
        return ""
    words = name.split()
    # Multi-word company/product titles are not person names.
    if len(words) >= 4:
        return ""
    return words[0].title()


def scrub_template_placeholders(
    text: str,
    *,
    recipient_name: str = "",
    sender_name: str = "",
    keep_sender_placeholder: bool = True,
) -> str:
    """Replace {{first_name}} / {{name}} etc. Never leave contact placeholders in queue text."""
    first = resolve_first_name(recipient_name)
    recipient = (recipient_name or "").strip()
    sender = (sender_name or "").strip()

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1).strip().lower()
        if key in {"sender_name", "sender", "your_name"}:
            if sender:
                return sender
            return match.group(0) if keep_sender_placeholder else ""
        if key in {"first_name", "firstname", "first"}:
            return first
        if key in {"name", "recipient_name", "contact_name", "full_name"}:
            return first or (recipient if recipient.lower() not in _GENERIC_NAMES else "")
        # Unknown placeholders — drop so they never reach the inbox/queue UI.
        return ""

    cleaned = _PLACEHOLDER_RE.sub(_replace, text or "")
    cleaned = _EMPTY_GREETING_RE.sub("", cleaned)
    # "Hi ," / "Hi  ," after empty first-name replacement
    cleaned = re.sub(r"(?im)^(?:hi|hello|hey)\s+,", "", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def contains_contact_placeholder(text: str) -> bool:
    for match in _PLACEHOLDER_RE.finditer(text or ""):
        key = match.group(1).strip().lower()
        if key not in {"sender_name", "sender", "your_name"}:
            return True
    return False
