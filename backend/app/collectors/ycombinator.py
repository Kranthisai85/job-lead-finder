"""Y Combinator collector (yc-oss public JSON)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.collectors.base import BaseCollector
from app.collectors.geo_india import india_match_score, prioritize_india_leads
from app.collectors.registry import CollectorRegistry
from app.collectors.types import CompanyLead
from app.collectors.ycombinator_client import fetch_yc_companies
from app.core.config import settings
from app.utils.url import is_usable_company_website
from app.core.timezone import now_app


@CollectorRegistry.register("ycombinator")
class YCombinatorCollector(BaseCollector):
    async def collect(self) -> list[Any]:
        self.logger.info("collector=%s status=collecting", self.name)
        companies = await fetch_yc_companies()
        self.logger.info("collector=%s products_found=%d", self.name, len(companies))
        return companies

    async def normalize(self, raw_items: list[Any]) -> list[CompanyLead]:
        leads: list[CompanyLead] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            website = str(item.get("website") or "").strip()
            name = str(item.get("name") or "").strip()
            if not name or not website or not is_usable_company_website(website):
                continue

            locations = str(item.get("all_locations") or "")
            regions = [str(r) for r in (item.get("regions") or []) if r]
            one_liner = str(item.get("one_liner") or item.get("long_description") or "")
            india_score = india_match_score(
                website=website,
                locations=locations,
                regions=regions,
                description=one_liner,
                name=name,
            )

            tags: list[str] = []
            industry = item.get("industry")
            if industry:
                tags.append(str(industry))
            for tag in item.get("tags") or []:
                if tag and str(tag) not in tags:
                    tags.append(str(tag))
            if india_score > 0:
                tags.append("india")

            launched_at = item.get("launched_at")
            discovered = now_app()
            if isinstance(launched_at, (int, float)) and launched_at > 0:
                discovered = datetime.fromtimestamp(float(launched_at), tz=timezone.utc)

            leads.append(
                CompanyLead(
                    name=name,
                    website=website,
                    description=one_liner or None,
                    source="ycombinator",
                    tags=tags,
                    discovered_at=discovered,
                    metadata={
                        "yc_id": item.get("id"),
                        "yc_slug": item.get("slug"),
                        "yc_url": item.get("url"),
                        "batch": item.get("batch"),
                        "all_locations": locations,
                        "regions": regions,
                        "stage": item.get("stage"),
                        "status": item.get("status"),
                        "india_score": india_score,
                        "prefer_india": bool(settings.prefer_india_startups),
                    },
                )
            )

        if settings.prefer_india_startups:
            leads = prioritize_india_leads(leads)

        limited = leads[: settings.ycombinator_max_companies]
        india_count = sum(1 for lead in limited if int((lead.metadata or {}).get("india_score") or 0) > 0)
        self.logger.info(
            "collector=%s normalized=%d india_prioritized=%d limit=%d",
            self.name,
            len(limited),
            india_count,
            settings.ycombinator_max_companies,
        )
        return limited

    @property
    def name(self) -> str:
        return "ycombinator"
