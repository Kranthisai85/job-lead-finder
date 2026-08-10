"""Tests for GitHub / RSS / Google News / Reddit collectors."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import app.collectors  # noqa: F401
from app.collectors.discovery_urls import pick_company_website
from app.collectors.factory import CollectorFactory
from app.collectors.registry import CollectorRegistry
from app.collectors.rss_client import parse_feed_xml
from app.source_manager.registry import SourceRegistry


def test_pick_company_website_skips_social_hosts() -> None:
    assert pick_company_website("https://github.com/acme/app", fallback_text="https://acme.dev") == (
        "https://acme.dev"
    )
    assert pick_company_website("https://acme.example") == "https://acme.example"


def test_parse_rss_xml() -> None:
    xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <title>Acme launches in India</title>
        <link>https://news.example/story</link>
        <description>Startup in Bangalore &lt;a href="https://acme.in"&gt;site&lt;/a&gt;</description>
        <pubDate>Mon, 10 Aug 2026 10:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """
    items = parse_feed_xml(xml)
    assert len(items) == 1
    assert items[0]["title"].startswith("Acme")


def test_new_collectors_registered() -> None:
    for name in ("github", "rss", "googlenews", "reddit"):
        assert name in CollectorRegistry.list()
        assert name in SourceRegistry.list()


@pytest.mark.asyncio
async def test_github_normalize_uses_homepage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.collectors.github.settings.github_max_companies", 10)
    monkeypatch.setattr("app.collectors.github.settings.prefer_india_startups", True)
    collector = CollectorFactory.create("github", MagicMock())
    leads = await collector.normalize(
        [
            {
                "id": 1,
                "name": "india-pay",
                "full_name": "org/india-pay",
                "description": "Payments in India",
                "homepage": "https://indiapay.example",
                "html_url": "https://github.com/org/india-pay",
                "pushed_at": "2026-08-01T00:00:00Z",
                "stargazers_count": 12,
            },
            {
                "id": 2,
                "name": "no-site",
                "full_name": "org/no-site",
                "description": "no homepage",
                "homepage": "",
                "html_url": "https://github.com/org/no-site",
                "pushed_at": "2026-08-01T00:00:00Z",
            },
        ]
    )
    assert len(leads) == 1
    assert leads[0].website == "https://indiapay.example"
    assert leads[0].source == "github"


@pytest.mark.asyncio
async def test_reddit_skips_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.collectors.reddit_client.settings.reddit_client_id", None)
    monkeypatch.setattr("app.collectors.reddit_client.settings.reddit_client_secret", None)
    collector = CollectorFactory.create("reddit", MagicMock())
    assert await collector.collect() == []


@pytest.mark.asyncio
async def test_rss_normalize(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.collectors.rss.settings.rss_max_companies", 5)
    monkeypatch.setattr("app.collectors.rss.settings.prefer_india_startups", True)
    collector = CollectorFactory.create("rss", MagicMock())
    leads = await collector.normalize(
        [
            {
                "title": "Mumbai startup launches app",
                "link": "https://publisher.example/story",
                "description": "Built in Mumbai",
                "raw_description": '<a href="https://mumbaico.in">site</a>',
                "published": "Mon, 10 Aug 2026 10:00:00 GMT",
                "feed_url": "https://example.com/feed",
            }
        ]
    )
    assert len(leads) == 1
    assert leads[0].source == "rss"
    assert "india" in leads[0].tags


@pytest.mark.asyncio
async def test_reddit_normalize(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.collectors.reddit.settings.reddit_max_companies", 5)
    collector = CollectorFactory.create("reddit", MagicMock())
    leads = await collector.normalize(
        [
            {
                "id": "abc",
                "title": "Show my India SaaS",
                "url": "https://indiasaas.example",
                "selftext": "Built in Bangalore",
                "subreddit": "indianstartups",
                "permalink": "/r/indianstartups/comments/abc/x/",
                "created_utc": 1750000000,
            }
        ]
    )
    assert len(leads) == 1
    assert leads[0].source == "reddit"
