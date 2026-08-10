"""RSS feed collector."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from app.collectors.base import BaseCollector
from app.collectors.discovery_urls import pick_company_website
from app.collectors.geo_india import india_match_score, prioritize_india_leads
from app.collectors.registry import CollectorRegistry
from app.collectors.rss_client import default_rss_feeds, fetch_rss_items
from app.collectors.types import CompanyLead
from app.core.config import settings
from app.utils.url import is_usable_company_website


def _parse_published(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError, IndexError):
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def normalize_rss_items(
    raw_items: list[Any],
    *,
    source_name: str,
    max_companies: int,
) -> list[CompanyLead]:
    leads: list[CompanyLead] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        description = str(item.get("description") or "")
        website = pick_company_website(
            item.get("link"),
            fallback_text=f"{item.get('raw_description') or ''} {description}",
        )
        if not website or not is_usable_company_website(website):
            continue

        india_score = india_match_score(
            website=website,
            description=description,
            name=title,
            extra=str(item.get("feed_url") or ""),
        )
        tags = [source_name]
        if india_score > 0:
            tags.append("india")

        leads.append(
            CompanyLead(
                name=title[:120],
                website=website,
                description=description[:400] or None,
                source=source_name,
                tags=tags,
                discovered_at=_parse_published(str(item.get("published") or "") or None),
                metadata={
                    "feed_url": item.get("feed_url"),
                    "item_link": item.get("link"),
                    "india_score": india_score,
                },
            )
        )

    if settings.prefer_india_startups:
        leads = prioritize_india_leads(leads)
    return leads[:max_companies]


@CollectorRegistry.register("rss")
class RssCollector(BaseCollector):
    async def collect(self) -> list[Any]:
        feeds = default_rss_feeds()
        self.logger.info("collector=%s status=collecting feeds=%d", self.name, len(feeds))
        if not feeds:
            self.logger.warning("collector=%s no_feeds_configured", self.name)
            return []
        items = await fetch_rss_items(feeds)
        self.logger.info("collector=%s products_found=%d", self.name, len(items))
        return items

    async def normalize(self, raw_items: list[Any]) -> list[CompanyLead]:
        leads = normalize_rss_items(
            raw_items,
            source_name="rss",
            max_companies=settings.rss_max_companies,
        )
        self.logger.info("collector=%s normalized=%d", self.name, len(leads))
        return leads

    @property
    def name(self) -> str:
        return "rss"
