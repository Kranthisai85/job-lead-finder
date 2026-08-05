from __future__ import annotations

from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


def is_producthunt_redirect(url: str) -> bool:
    """Return True when *url* is a Product Hunt short redirect (/r/...)."""
    cleaned = url.strip()
    if not cleaned:
        return False

    parsed = urlparse(cleaned)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host != "producthunt.com":
        return False
    return parsed.path.startswith("/r/")


async def resolve_producthunt_redirect(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Follow Product Hunt redirect URLs and return the final destination.

    Non-redirect URLs are returned unchanged. Failures are logged and the
    original URL is returned so the collector can continue.
    """
    cleaned = url.strip()
    if not cleaned or not is_producthunt_redirect(cleaned):
        return cleaned or url

    owns_client = client is None
    http_client = client or httpx.AsyncClient(
        follow_redirects=True,
        timeout=settings.product_hunt_timeout,
    )

    try:
        response = await http_client.get(cleaned)
        final_url = str(response.url).strip()
        if not final_url:
            logger.warning(
                "producthunt_redirect_empty original=%s status=%s",
                cleaned,
                response.status_code,
            )
            return cleaned

        if final_url != cleaned:
            logger.info(
                "producthunt_redirect_resolved original=%s final=%s status=%s",
                cleaned,
                final_url,
                response.status_code,
            )
        return final_url
    except Exception as exc:
        logger.warning(
            "producthunt_redirect_failed original=%s error=%s",
            cleaned,
            exc,
        )
        return cleaned
    finally:
        if owns_client:
            await http_client.aclose()
