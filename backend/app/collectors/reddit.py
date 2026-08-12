"""Reddit collector for startup / side-project subreddits."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.collectors.base import BaseCollector
from app.collectors.discovery_urls import pick_company_website
from app.collectors.geo_india import india_match_score, prioritize_india_leads
from app.collectors.reddit_client import RedditCredentialsMissing, fetch_reddit_posts
from app.collectors.registry import CollectorRegistry
from app.collectors.types import CompanyLead
from app.core.config import settings
from app.utils.url import is_usable_company_website
from app.core.timezone import now_app


@CollectorRegistry.register("reddit")
class RedditCollector(BaseCollector):
    async def collect(self) -> list[Any]:
        self.logger.info("collector=%s status=collecting", self.name)
        try:
            posts = await fetch_reddit_posts()
        except RedditCredentialsMissing as exc:
            self.logger.warning("collector=%s skipped reason=%s", self.name, exc)
            return []
        self.logger.info("collector=%s products_found=%d", self.name, len(posts))
        return posts

    async def normalize(self, raw_items: list[Any]) -> list[CompanyLead]:
        leads: list[CompanyLead] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            selftext = str(item.get("selftext") or "")
            subreddit = str(item.get("subreddit") or "")
            website = pick_company_website(
                item.get("url_overridden_by_dest"),
                item.get("url"),
                fallback_text=selftext,
            )
            if not website or not is_usable_company_website(website):
                continue

            india_score = india_match_score(
                website=website,
                description=selftext,
                name=title,
                extra=subreddit,
            )
            if subreddit.lower() in {"indianstartups", "developersindia"}:
                india_score = max(india_score, 40)
            tags = ["reddit", subreddit]
            if india_score > 0:
                tags.append("india")

            created = item.get("created_utc")
            discovered = now_app()
            if isinstance(created, (int, float)) and created > 0:
                discovered = datetime.fromtimestamp(float(created), tz=timezone.utc)

            leads.append(
                CompanyLead(
                    name=title[:120],
                    website=website,
                    description=(selftext[:400] if selftext else None),
                    source="reddit",
                    tags=[tag for tag in tags if tag],
                    discovered_at=discovered,
                    metadata={
                        "reddit_id": item.get("id"),
                        "reddit_permalink": (
                            f"https://www.reddit.com{item.get('permalink')}"
                            if item.get("permalink")
                            else None
                        ),
                        "subreddit": item.get("subreddit"),
                        "india_score": india_score,
                    },
                )
            )

        if settings.prefer_india_startups:
            leads = prioritize_india_leads(leads)
        limited = leads[: settings.reddit_max_companies]
        self.logger.info("collector=%s normalized=%d", self.name, len(limited))
        return limited

    @property
    def name(self) -> str:
        return "reddit"
