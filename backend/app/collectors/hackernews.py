"""Hacker News Show HN collector."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.collectors.base import BaseCollector
from app.collectors.geo_india import india_match_score, prioritize_india_leads
from app.collectors.hackernews_client import fetch_show_hn_posts, parse_show_hn_title
from app.collectors.registry import CollectorRegistry
from app.collectors.types import CompanyLead
from app.core.config import settings
from app.utils.url import is_usable_company_website
from app.core.timezone import now_app


@CollectorRegistry.register("hackernews")
class HackerNewsCollector(BaseCollector):
    async def collect(self) -> list[Any]:
        self.logger.info("collector=%s status=collecting", self.name)
        posts = await fetch_show_hn_posts()
        self.logger.info("collector=%s products_found=%d", self.name, len(posts))
        return posts

    async def normalize(self, raw_items: list[Any]) -> list[CompanyLead]:
        leads: list[CompanyLead] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            website = str(item.get("url") or "").strip()
            if not website or not is_usable_company_website(website):
                continue

            title = str(item.get("title") or "").strip()
            name, tagline = parse_show_hn_title(title)
            if not name:
                continue

            story_text = str(item.get("story_text") or "")
            india_score = india_match_score(
                website=website,
                description=tagline or "",
                name=name,
                extra=f"{title} {story_text}",
            )
            created = item.get("created_at")
            discovered = now_app()
            if isinstance(created, str) and created:
                try:
                    discovered = datetime.fromisoformat(created.replace("Z", "+00:00"))
                except ValueError:
                    pass

            tags = ["show_hn"]
            if india_score > 0:
                tags.append("india")

            leads.append(
                CompanyLead(
                    name=name,
                    website=website,
                    description=tagline or (story_text[:280] if story_text else None),
                    source="hackernews",
                    tags=tags,
                    discovered_at=discovered,
                    metadata={
                        "hn_object_id": item.get("objectID"),
                        "hn_url": f"https://news.ycombinator.com/item?id={item.get('objectID')}",
                        "hn_author": item.get("author"),
                        "hn_points": item.get("points"),
                        "india_score": india_score,
                        "prefer_india": bool(settings.prefer_india_startups),
                    },
                )
            )

        if settings.prefer_india_startups:
            leads = prioritize_india_leads(leads)

        limited = leads[: settings.hackernews_max_companies]
        india_count = sum(1 for lead in limited if int((lead.metadata or {}).get("india_score") or 0) > 0)
        self.logger.info(
            "collector=%s normalized=%d india_prioritized=%d limit=%d",
            self.name,
            len(limited),
            india_count,
            settings.hackernews_max_companies,
        )
        return limited

    @property
    def name(self) -> str:
        return "hackernews"
