"""GitHub Search API client — free; token optional for higher rate limits."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


async def fetch_github_repositories(
    *,
    client: httpx.AsyncClient | None = None,
    max_items: int | None = None,
) -> list[dict[str, Any]]:
    limit = max_items if max_items is not None else settings.github_max_companies
    per_page = max(limit, min(100, limit * 2))
    since = (datetime.now(timezone.utc) - timedelta(days=settings.github_lookback_days)).date().isoformat()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": settings.github_user_agent,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = (settings.github_token or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=settings.github_timeout)
    try:
        india = await _search(
            http_client,
            headers=headers,
            query=(
                f"({settings.github_india_query}) in:name,description,readme "
                f"pushed:>{since}"
            ),
            per_page=per_page,
        )
        general = await _search(
            http_client,
            headers=headers,
            query=f"stars:>{settings.github_min_stars} pushed:>{since}",
            per_page=per_page,
        )
    finally:
        if owns_client:
            await http_client.aclose()

    merged = _dedupe(india + general)
    logger.info(
        "collector=github india_hits=%d general_hits=%d merged=%d token=%s",
        len(india),
        len(general),
        len(merged),
        "yes" if token else "no",
    )
    return merged


async def _search(
    client: httpx.AsyncClient,
    *,
    headers: dict[str, str],
    query: str,
    per_page: int,
) -> list[dict[str, Any]]:
    response = await client.get(
        f"{settings.github_api_base.rstrip('/')}/search/repositories",
        headers=headers,
        params={
            "q": query,
            "sort": "updated",
            "order": "desc",
            "per_page": per_page,
        },
    )
    if response.status_code == 403:
        logger.warning("collector=github rate_limited detail=%s", response.text[:200])
        return []
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = str(item.get("id") or item.get("full_name") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
