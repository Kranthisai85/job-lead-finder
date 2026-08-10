"""GitHub repository → company website collector."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.collectors.base import BaseCollector
from app.collectors.discovery_urls import pick_company_website
from app.collectors.geo_india import india_match_score, prioritize_india_leads
from app.collectors.github_client import fetch_github_repositories
from app.collectors.registry import CollectorRegistry
from app.collectors.types import CompanyLead
from app.core.config import settings
from app.utils.url import is_usable_company_website


@CollectorRegistry.register("github")
class GitHubCollector(BaseCollector):
    async def collect(self) -> list[Any]:
        self.logger.info("collector=%s status=collecting", self.name)
        repos = await fetch_github_repositories()
        self.logger.info("collector=%s products_found=%d", self.name, len(repos))
        return repos

    async def normalize(self, raw_items: list[Any]) -> list[CompanyLead]:
        leads: list[CompanyLead] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            description = str(item.get("description") or "")
            website = pick_company_website(
                item.get("homepage"),
                fallback_text=description,
            )
            if not website or not is_usable_company_website(website):
                continue

            india_score = india_match_score(
                website=website,
                description=description,
                name=name,
                extra=str(item.get("full_name") or ""),
            )
            tags = ["github"]
            if india_score > 0:
                tags.append("india")

            pushed = item.get("pushed_at") or item.get("updated_at")
            discovered = datetime.now(timezone.utc)
            if isinstance(pushed, str) and pushed:
                try:
                    discovered = datetime.fromisoformat(pushed.replace("Z", "+00:00"))
                except ValueError:
                    pass

            leads.append(
                CompanyLead(
                    name=name,
                    website=website,
                    description=description or None,
                    source="github",
                    tags=tags,
                    discovered_at=discovered,
                    metadata={
                        "github_full_name": item.get("full_name"),
                        "github_html_url": item.get("html_url"),
                        "github_stars": item.get("stargazers_count"),
                        "india_score": india_score,
                    },
                )
            )

        if settings.prefer_india_startups:
            leads = prioritize_india_leads(leads)
        limited = leads[: settings.github_max_companies]
        self.logger.info(
            "collector=%s normalized=%d india=%d",
            self.name,
            len(limited),
            sum(1 for lead in limited if int((lead.metadata or {}).get("india_score") or 0) > 0),
        )
        return limited

    @property
    def name(self) -> str:
        return "github"
