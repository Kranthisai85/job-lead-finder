"""Reddit OAuth client — free app credentials required."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class RedditCredentialsMissing(RuntimeError):
    pass


async def fetch_reddit_posts(
    *,
    client: httpx.AsyncClient | None = None,
    max_items: int | None = None,
) -> list[dict[str, Any]]:
    client_id = (settings.reddit_client_id or "").strip()
    client_secret = (settings.reddit_client_secret or "").strip()
    if not client_id or not client_secret:
        raise RedditCredentialsMissing(
            "REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are required for the reddit collector"
        )

    limit = max_items if max_items is not None else settings.reddit_max_companies
    per_sub = max(10, min(100, limit))
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=settings.reddit_timeout)
    try:
        token = await _fetch_token(http_client, client_id=client_id, client_secret=client_secret)
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": settings.reddit_user_agent,
        }
        # Fetch India-focused subreddits first so they win dedupe order.
        posts: list[dict[str, Any]] = []
        for subreddit in _subreddits():
            try:
                response = await http_client.get(
                    f"https://oauth.reddit.com/r/{subreddit}/new",
                    headers=headers,
                    params={"limit": per_sub, "raw_json": 1},
                )
                response.raise_for_status()
                payload = response.json()
                children = (
                    (((payload or {}).get("data") or {}).get("children"))
                    if isinstance(payload, dict)
                    else None
                )
                if not isinstance(children, list):
                    continue
                for child in children:
                    if not isinstance(child, dict):
                        continue
                    data = child.get("data")
                    if isinstance(data, dict):
                        data = {**data, "subreddit": data.get("subreddit") or subreddit}
                        posts.append(data)
                logger.info("collector=reddit subreddit=%s posts=%d", subreddit, len(children))
            except Exception as exc:  # noqa: BLE001
                logger.warning("collector=reddit subreddit=%s error=%s", subreddit, exc)

        # Extra India keyword search across configured subs.
        try:
            response = await http_client.get(
                "https://oauth.reddit.com/search",
                headers=headers,
                params={
                    "q": "India OR Bangalore OR Bengaluru OR Mumbai OR Hyderabad OR Chennai OR Pune startup",
                    "sort": "new",
                    "limit": per_sub,
                    "raw_json": 1,
                    "type": "link",
                },
            )
            response.raise_for_status()
            payload = response.json()
            children = (
                (((payload or {}).get("data") or {}).get("children"))
                if isinstance(payload, dict)
                else None
            )
            if isinstance(children, list):
                for child in children:
                    if not isinstance(child, dict):
                        continue
                    data = child.get("data")
                    if isinstance(data, dict):
                        posts.insert(0, data)
                logger.info("collector=reddit india_search_posts=%d", len(children))
        except Exception as exc:  # noqa: BLE001
            logger.warning("collector=reddit india_search_error=%s", exc)
    finally:
        if owns_client:
            await http_client.aclose()

    return _dedupe(posts)


async def _fetch_token(
    client: httpx.AsyncClient,
    *,
    client_id: str,
    client_secret: str,
) -> str:
    response = await client.post(
        "https://www.reddit.com/api/v1/access_token",
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        headers={"User-Agent": settings.reddit_user_agent},
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not token:
        raise RuntimeError("Reddit OAuth did not return access_token")
    return str(token)


def _subreddits() -> list[str]:
    raw = settings.reddit_subreddits or ""
    return [part.strip().lstrip("r/") for part in raw.split(",") if part.strip()]


def _dedupe(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for post in posts:
        key = str(post.get("id") or post.get("name") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(post)
    return out
