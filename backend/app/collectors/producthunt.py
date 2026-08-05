from datetime import datetime, timezone
from typing import Any

from playwright.async_api import Page

from app.collectors.base import BaseCollector
from app.collectors.producthunt_parser import (
    extract_topics,
    fetch_latest_product_hunt_posts,
    parse_launch_date,
)
from app.collectors.producthunt_redirect import (
    producthunt_browser_page,
    raw_items_need_website_resolution,
    resolve_company_website,
)
from app.collectors.registry import CollectorRegistry
from app.collectors.types import CompanyLead
from app.exceptions import DuplicateRecordError
from app.schemas.company import CreateCompanyRequest


@CollectorRegistry.register("producthunt")
class ProductHuntCollector(BaseCollector):
    async def collect(self) -> list[Any]:
        self.logger.info("collector=%s status=collecting", self.name)
        products, pages_fetched = await fetch_latest_product_hunt_posts()
        self.logger.info(
            "collector=%s pages_fetched=%d products_found=%d",
            self.name,
            pages_fetched,
            len(products),
        )
        return products

    async def normalize(self, raw_items: list[Any]) -> list[CompanyLead]:
        leads: list[CompanyLead] = []

        if raw_items_need_website_resolution(raw_items):
            async with producthunt_browser_page() as page:
                for item in raw_items:
                    lead = await self._normalize_item(item, page=page)
                    if lead is not None:
                        leads.append(lead)
            return leads

        for item in raw_items:
            lead = await self._normalize_item(item, page=None)
            if lead is not None:
                leads.append(lead)
        return leads

    async def _normalize_item(
        self,
        item: Any,
        *,
        page: Page | None,
    ) -> CompanyLead | None:
        if not isinstance(item, dict):
            return None

        website = item.get("website")
        if not website or not str(website).strip():
            return None

        raw_website = str(website).strip()
        product_page_url = item.get("url")
        resolved_website = await resolve_company_website(
            raw_website,
            product_page_url=str(product_page_url) if product_page_url else None,
            page=page,
        )
        if not resolved_website.strip():
            return None

        topics = extract_topics(item)
        launch_date = item.get("createdAt")
        parsed_launch_date = parse_launch_date(str(launch_date) if launch_date else None)

        metadata: dict[str, Any] = {
            "product_hunt_url": product_page_url,
            "launch_date": launch_date,
            "topics": topics,
            "slug": item.get("slug"),
            "product_hunt_id": item.get("id"),
        }
        if resolved_website != raw_website:
            metadata["website_redirect"] = raw_website

        return CompanyLead(
            name=str(item["name"]),
            website=resolved_website,
            description=(str(item["tagline"]) if item.get("tagline") else None),
            source="producthunt",
            tags=topics,
            discovered_at=parsed_launch_date or datetime.now(timezone.utc),
            metadata=metadata,
        )

    async def save(self, leads: list[CompanyLead]) -> int:
        saved_count = 0
        skipped_duplicates = 0

        for lead in leads:
            industry = lead.tags[0] if lead.tags else None
            try:
                await self.company_service.create_company(
                    CreateCompanyRequest(
                        name=lead.name,
                        website=lead.website,
                        description=lead.description,
                        industry=industry,
                        source=lead.source,
                    )
                )
                saved_count += 1
            except DuplicateRecordError:
                skipped_duplicates += 1
                self.logger.info(
                    "collector=%s action=skip_duplicate website=%s",
                    self.name,
                    lead.website,
                )

        self.logger.info(
            "collector=%s products_saved=%d skipped_duplicates=%d",
            self.name,
            saved_count,
            skipped_duplicates,
        )
        return saved_count

    @property
    def name(self) -> str:
        return "producthunt"
