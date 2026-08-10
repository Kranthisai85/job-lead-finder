"""Shared helpers for extracting company websites from discovery posts."""

from __future__ import annotations

import re
from urllib.parse import urlparse

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)

_BLOCKED_HOST_SUFFIXES = (
    "github.com",
    "githubusercontent.com",
    "reddit.com",
    "redd.it",
    "news.ycombinator.com",
    "producthunt.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "youtu.be",
    "medium.com",
    "news.google.com",
    "google.com",
    "t.co",
    "bit.ly",
)


def iter_urls(text: str | None) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(".,);]")
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(url)
    return found


def is_blocked_discovery_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return True
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in _BLOCKED_HOST_SUFFIXES)


def pick_company_website(*candidates: str | None, fallback_text: str = "") -> str | None:
    """Prefer an explicit external homepage over social / forge links."""
    ordered: list[str] = []
    for candidate in candidates:
        if candidate and str(candidate).strip():
            ordered.append(str(candidate).strip())
    ordered.extend(iter_urls(fallback_text))
    for url in ordered:
        if not is_blocked_discovery_host(url):
            return url
    return None
