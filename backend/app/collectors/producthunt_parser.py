from datetime import datetime
from typing import Any

import httpx

from app.collectors.producthunt_client import PRODUCT_HUNT_POSTS_QUERY
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


def parse_product_hunt_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    data = payload.get("data")
    if not isinstance(data, dict):
        return []

    posts = data.get("posts")
    if not isinstance(posts, dict):
        return []

    edges = posts.get("edges")
    if not isinstance(edges, list):
        return []

    products: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        node = edge.get("node")
        if not isinstance(node, dict):
            continue
        if not node.get("name"):
            continue
        products.append(node)

    return products


async def fetch_latest_product_hunt_posts(
    *,
    client: httpx.AsyncClient | None = None,
) -> tuple[list[dict[str, Any]], int]:
    headers = {
        "User-Agent": settings.product_hunt_user_agent,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if settings.product_hunt_api_token:
        headers["Authorization"] = f"Bearer {settings.product_hunt_api_token}"

    request_body = {
        "query": PRODUCT_HUNT_POSTS_QUERY,
        "variables": {"first": settings.product_hunt_max_companies},
    }

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=settings.product_hunt_timeout)

    try:
        response = await http_client.post(
            settings.product_hunt_api_url,
            json=request_body,
            headers=headers,
        )
        response.raise_for_status()
        payload = response.json()
        products = parse_product_hunt_response(payload)
        return products, 1
    except Exception:
        logger.exception("Product Hunt request failed")
        return [], 0
    finally:
        if owns_client:
            await http_client.aclose()


def extract_topics(product: dict[str, Any]) -> list[str]:
    topics_block = product.get("topics")
    if not isinstance(topics_block, dict):
        return []

    edges = topics_block.get("edges")
    if not isinstance(edges, list):
        return []

    topics: list[str] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        node = edge.get("node")
        if isinstance(node, dict) and node.get("name"):
            topics.append(str(node["name"]))
    return topics


def parse_launch_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None
