"""Y Combinator company list client via yc-oss (free, no API key)."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# Recent + current batches — keep this short so daily runs stay light.
DEFAULT_BATCH_SLUGS: tuple[str, ...] = (
    "winter-2026",
    "fall-2025",
    "summer-2025",
    "spring-2025",
    "winter-2025",
)


async def fetch_yc_companies(
    *,
    client: httpx.AsyncClient | None = None,
    batch_slugs: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    slugs = batch_slugs or DEFAULT_BATCH_SLUGS
    headers = {"User-Agent": settings.ycombinator_user_agent}
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=settings.ycombinator_timeout)
    companies: list[dict[str, Any]] = []

    try:
        for slug in slugs:
            url = f"{settings.ycombinator_api_base.rstrip('/')}/batches/{slug}.json"
            try:
                response = await http_client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:  # noqa: BLE001 — one bad batch must not kill the run
                logger.warning("collector=ycombinator batch=%s error=%s", slug, exc)
                continue
            if not isinstance(payload, list):
                continue
            for item in payload:
                if isinstance(item, dict) and item.get("website") and item.get("name"):
                    companies.append(item)
    finally:
        if owns_client:
            await http_client.aclose()

    deduped = _dedupe_companies(companies)
    logger.info(
        "collector=ycombinator batches=%d companies=%d",
        len(slugs),
        len(deduped),
    )
    return deduped


def _dedupe_companies(companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for company in companies:
        key = str(company.get("id") or company.get("slug") or company.get("website") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(company)
    return out
