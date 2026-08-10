"""Normalize scraped company titles into short brand names for outreach."""

from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")
_TAGLINE_SEPARATORS = (": ", " — ", " – ", " - ", " | ")


def clean_company_display_name(name: str | None) -> str:
    """Strip marketing taglines from titles like 'Pesterly: somebody has to nag...'."""
    cleaned = _WHITESPACE_RE.sub(" ", (name or "").strip())
    if not cleaned:
        return ""

    for sep in _TAGLINE_SEPARATORS:
        if sep not in cleaned:
            continue
        left, right = cleaned.split(sep, 1)
        left = left.strip()
        right = right.strip()
        if not left:
            continue
        # Prefer brand when the right side looks like a slogan / subtitle.
        if len(left) <= 40 and (len(right) >= 8 or len(cleaned) > 35):
            cleaned = left
            break

    return cleaned.strip()


def prefer_company_name(*, seed_name: str | None, profile_name: str | None) -> str:
    """Prefer the collector seed when the profile name is a polluted title."""
    seed = clean_company_display_name(seed_name)
    profile = clean_company_display_name(profile_name)
    if seed and profile:
        seed_l = seed.lower()
        profile_l = profile.lower()
        if seed_l == profile_l:
            return seed
        if seed_l in profile_l and len(profile) > len(seed) + 3:
            return seed
        if profile_l in seed_l and len(seed) > len(profile) + 3:
            return profile
        # Prefer the shorter brand-like name when both exist.
        if abs(len(profile) - len(seed)) >= 10:
            return seed if len(seed) < len(profile) else profile
        return seed
    return seed or profile or "your company"
