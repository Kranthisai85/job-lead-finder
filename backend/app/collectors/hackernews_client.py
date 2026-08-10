"""Hacker News Algolia client (Show HN) — free, no API key."""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_SHOW_HN_PREFIX = re.compile(r"^Show\s+HN:\s*", re.IGNORECASE)
_INDIA_QUERY = (
    "India OR Bangalore OR Bengaluru OR Mumbai OR Delhi OR Hyderabad OR "
    "Chennai OR Pune OR Kolkata OR Gurugram OR Noida"
)


def parse_show_hn_title(title: str) -> tuple[str, str | None]:
    cleaned = _SHOW_HN_PREFIX.sub("", (title or "").strip()).strip()
    if not cleaned:
        return "", None
    for separator in (" – ", " — ", " - ", ": "):
        if separator in cleaned:
            name, remainder = cleaned.split(separator, 1)
            name = name.strip()
            remainder = remainder.strip()
            if name:
                return name, remainder or None
    return cleaned, None


async def fetch_show_hn_posts(
    *,
    client: httpx.AsyncClient | None = None,
    max_items: int | None = None,
) -> list[dict[str, Any]]:
    limit = max_items if max_items is not None else settings.hackernews_max_companies
    # Over-fetch so India prioritization still has a pool after filtering.
    per_query = max(limit, min(100, limit * 2))
    headers = {"User-Agent": settings.hackernews_user_agent}
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=settings.hackernews_timeout)

    try:
        general = await _search(
            http_client,
            headers=headers,
            query="",
            hits_per_page=per_query,
        )
        india = await _search(
            http_client,
            headers=headers,
            query=_INDIA_QUERY,
            hits_per_page=per_query,
        )
    finally:
        if owns_client:
            await http_client.aclose()

    merged = _dedupe_hits(india + general)
    logger.info(
        "collector=hackernews hits_india=%d hits_general=%d merged=%d",
        len(india),
        len(general),
        len(merged),
    )
    return merged


async def _search(
    client: httpx.AsyncClient,
    *,
    headers: dict[str, str],
    query: str,
    hits_per_page: int,
) -> list[dict[str, Any]]:
    response = await client.get(
        settings.hackernews_api_url,
        headers=headers,
        params={
            "tags": "show_hn",
            "hitsPerPage": hits_per_page,
            "query": query,
        },
    )
    response.raise_for_status()
    payload = response.json()
    hits = payload.get("hits") if isinstance(payload, dict) else None
    if not isinstance(hits, list):
        return []
    return [hit for hit in hits if isinstance(hit, dict)]


def _dedupe_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for hit in hits:
        key = str(hit.get("objectID") or hit.get("story_id") or hit.get("url") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(hit)
    return out
