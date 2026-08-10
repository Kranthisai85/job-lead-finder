"""Tests for Hacker News + YC collectors and India prioritization."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.collectors  # noqa: F401
from app.collectors.factory import CollectorFactory
from app.collectors.geo_india import india_match_score, prioritize_india_leads
from app.collectors.hackernews_client import parse_show_hn_title
from app.collectors.registry import CollectorRegistry
from app.collectors.types import CompanyLead
from app.source_manager.registry import SourceRegistry


def test_parse_show_hn_title() -> None:
    assert parse_show_hn_title("Show HN: Acme – billing for startups") == (
        "Acme",
        "billing for startups",
    )
    assert parse_show_hn_title("Show HN: SoloTool") == ("SoloTool", None)


def test_india_match_score_location_and_tld() -> None:
    assert india_match_score(locations="Bangalore, India", website="https://acme.com") >= 50
    assert india_match_score(website="https://acme.co.in") >= 40
    assert india_match_score(website="https://acme.com", description="US only") == 0


def test_prioritize_india_leads_orders_indian_first() -> None:
    leads = [
        CompanyLead(name="US Co", website="https://us.example", source="hackernews", metadata={"india_score": 0}),
        CompanyLead(name="IN Co", website="https://in.example", source="hackernews", metadata={"india_score": 50}),
    ]
    ordered = prioritize_india_leads(leads)
    assert ordered[0].name == "IN Co"
    assert ordered[1].name == "US Co"


def test_collectors_registered() -> None:
    assert CollectorRegistry.get("hackernews").__name__ == "HackerNewsCollector"
    assert CollectorRegistry.get("ycombinator").__name__ == "YCombinatorCollector"
    assert "hackernews" in SourceRegistry.list()
    assert "ycombinator" in SourceRegistry.list()


@pytest.mark.asyncio
async def test_hackernews_normalize_prioritizes_india(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.collectors.hackernews.settings.hackernews_max_companies", 2)
    monkeypatch.setattr("app.collectors.hackernews.settings.prefer_india_startups", True)

    company_service = MagicMock()
    collector = CollectorFactory.create("hackernews", company_service)
    raw = [
        {
            "objectID": "1",
            "title": "Show HN: GlobalApp – analytics",
            "url": "https://global.example",
            "created_at": "2026-08-01T00:00:00Z",
        },
        {
            "objectID": "2",
            "title": "Show HN: BharatPay – UPI for India",
            "url": "https://bharatpay.example",
            "created_at": "2026-08-01T00:00:00Z",
            "story_text": "Built in Bangalore",
        },
        {
            "objectID": "3",
            "title": "Show HN: DelhiDesk – coworking",
            "url": "https://delhidesk.in",
            "created_at": "2026-08-01T00:00:00Z",
        },
    ]
    leads = await collector.normalize(raw)
    assert len(leads) == 2
    assert all(int(lead.metadata.get("india_score") or 0) > 0 for lead in leads)


@pytest.mark.asyncio
async def test_ycombinator_normalize_prioritizes_india(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.collectors.ycombinator.settings.ycombinator_max_companies", 2)
    monkeypatch.setattr("app.collectors.ycombinator.settings.prefer_india_startups", True)

    company_service = MagicMock()
    collector = CollectorFactory.create("ycombinator", company_service)
    raw: list[dict[str, Any]] = [
        {
            "id": 1,
            "name": "US Startup",
            "website": "https://usstartup.example",
            "one_liner": "US payroll",
            "all_locations": "San Francisco, CA, USA",
            "regions": ["United States", "America"],
            "industry": "B2B",
            "tags": [],
            "launched_at": 1700000000,
        },
        {
            "id": 2,
            "name": "India Startup",
            "website": "https://indiastartup.example",
            "one_liner": "Fintech for India",
            "all_locations": "Bengaluru, India",
            "regions": ["India", "South Asia"],
            "industry": "Fintech",
            "tags": [],
            "launched_at": 1700000001,
        },
        {
            "id": 3,
            "name": "Mumbai Co",
            "website": "https://mumbaico.in",
            "one_liner": "Logistics",
            "all_locations": "Mumbai, Maharashtra, India",
            "regions": ["India"],
            "industry": "B2B",
            "tags": [],
            "launched_at": 1700000002,
        },
    ]
    leads = await collector.normalize(raw)
    assert len(leads) == 2
    assert leads[0].name in {"India Startup", "Mumbai Co"}
    assert leads[1].name in {"India Startup", "Mumbai Co"}


@pytest.mark.asyncio
async def test_hackernews_collect_uses_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.collectors.hackernews.fetch_show_hn_posts",
        AsyncMock(return_value=[{"objectID": "9", "title": "Show HN: X", "url": "https://x.example"}]),
    )
    collector = CollectorFactory.create("hackernews", MagicMock())
    items = await collector.collect()
    assert len(items) == 1
