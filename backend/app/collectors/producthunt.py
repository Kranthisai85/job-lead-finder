from datetime import datetime, timezone
from typing import Any

import httpx

from app.collectors.base import BaseCollector
from app.collectors.producthunt_parser import (
    extract_topics,
    fetch_latest_product_hunt_posts,
    parse_launch_date,
)
from app.collectors.producthunt_redirect import resolve_producthunt_redirect
from app.collectors.registry import CollectorRegistry
from app.collectors.types import CompanyLead
from app.core.config import settings
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

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=settings.product_hunt_timeout,
        ) as client:
            for item in raw_items:
                if not isinstance(item, dict):
                    continue

                website = item.get("website")
                if not website or not str(website).strip():
                    continue

                resolved_website = await resolve_producthunt_redirect(
                    str(website),
                    client=client,
                )
                if not resolved_website.strip():
                    continue

                topics = extract_topics(item)
                launch_date = item.get("createdAt")
                parsed_launch_date = parse_launch_date(str(launch_date) if launch_date else None)

                leads.append(
                    CompanyLead(
                        name=str(item["name"]),
                        website=resolved_website,
                        description=(str(item["tagline"]) if item.get("tagline") else None),
                        source="producthunt",
                        tags=topics,
                        discovered_at=parsed_launch_date or datetime.now(timezone.utc),
                        metadata={
                            "product_hunt_url": item.get("url"),
                            "launch_date": launch_date,
                            "topics": topics,
                            "slug": item.get("slug"),
                            "product_hunt_id": item.get("id"),
                        },
                    )
                )

        return leads

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
