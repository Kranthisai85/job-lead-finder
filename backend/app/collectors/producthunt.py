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
    WebsiteResolution,
    is_cloudflare_blocked,
    is_producthunt_redirect,
    producthunt_browser_page,
    raw_items_need_website_resolution,
    resolve_company_website,
    strip_tracking_params,
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
        resolved_count = 0
        unresolved_count = 0

        async def _process(items: list[Any], page: Page | None) -> None:
            nonlocal resolved_count, unresolved_count
            for item in items:
                active_page = None if page is None or is_cloudflare_blocked() else page
                lead, resolved = await self._normalize_item(item, page=active_page)
                if lead is None:
                    continue
                leads.append(lead)
                if resolved:
                    resolved_count += 1
                else:
                    unresolved_count += 1

        try:
            if raw_items_need_website_resolution(raw_items):
                async with producthunt_browser_page() as page:
                    await _process(raw_items, page)
            else:
                await _process(raw_items, None)
        except Exception as exc:
            self.logger.warning(
                "collector=%s website_resolution_session_failed error=%s "
                "continuing_with_redirect_urls=true",
                self.name,
                exc,
            )
            seen_ids = {lead.metadata.get("product_hunt_id") for lead in leads}
            remaining = [
                item
                for item in raw_items
                if isinstance(item, dict) and item.get("id") not in seen_ids
            ]
            await _process(remaining, None)

        self.logger.info(
            "collector=%s websites_resolved=%d websites_unresolved=%d leads=%d",
            self.name,
            resolved_count,
            unresolved_count,
            len(leads),
        )
        return leads

    async def _normalize_item(
        self,
        item: Any,
        *,
        page: Page | None,
    ) -> tuple[CompanyLead | None, bool]:
        if not isinstance(item, dict):
            return None, False

        website = item.get("website")
        if not website or not str(website).strip():
            return None, False

        raw_website = strip_tracking_params(str(website).strip())
        product_page_url = item.get("url")

        resolution: WebsiteResolution = await resolve_company_website(
            raw_website,
            product_page_url=str(product_page_url) if product_page_url else None,
            page=page,
        )

        final_website = resolution.website.strip() or raw_website
        resolved = bool(resolution.resolved) and not is_producthunt_redirect(final_website)

        topics = extract_topics(item)
        launch_date = item.get("createdAt")
        parsed_launch_date = parse_launch_date(str(launch_date) if launch_date else None)

        metadata: dict[str, Any] = {
            "product_hunt_url": product_page_url,
            "launch_date": launch_date,
            "topics": topics,
            "slug": item.get("slug"),
            "product_hunt_id": item.get("id"),
            "website_redirect": raw_website,
            "website_resolution_failed": not resolved,
        }
        if resolution.source:
            metadata["website_resolution_source"] = resolution.source

        lead = CompanyLead(
            name=str(item["name"]),
            website=final_website,
            description=(str(item["tagline"]) if item.get("tagline") else None),
            source="producthunt",
            tags=topics,
            discovered_at=parsed_launch_date or datetime.now(timezone.utc),
            metadata=metadata,
        )
        return lead, resolved

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
