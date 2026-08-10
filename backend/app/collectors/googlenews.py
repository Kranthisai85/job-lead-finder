"""Google News RSS collector (no API key)."""

from __future__ import annotations

from typing import Any

from app.collectors.base import BaseCollector
from app.collectors.registry import CollectorRegistry
from app.collectors.rss import normalize_rss_items
from app.collectors.rss_client import default_google_news_feeds, fetch_rss_items
from app.collectors.types import CompanyLead
from app.core.config import settings


@CollectorRegistry.register("googlenews")
class GoogleNewsCollector(BaseCollector):
    async def collect(self) -> list[Any]:
        feeds = default_google_news_feeds()
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
            source_name="googlenews",
            max_companies=settings.google_news_max_companies,
        )
        self.logger.info("collector=%s normalized=%d", self.name, len(leads))
        return leads

    @property
    def name(self) -> str:
        return "googlenews"
