from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.contact_discovery.types import ContactCandidate, ContactDiscoveryReport
from app.crawler.types import WebsiteProfile
from app.validation.report import render_report
from app.validation.types import (
    CompanyValidationResult,
    StartupSeed,
    ValidationReport,
    ValidationSummary,
    compute_lead_score,
    count_decision_makers,
)
from app.validation.validation_runner import ValidationPipeline, load_startups

SAMPLE_HTML = """
<html>
  <head>
    <title>Acme Labs</title>
    <meta name="description" content="Acme builds modern workflow tools for startups worldwide." />
    <script id="__NEXT_DATA__" type="application/json">{}</script>
    <script src="https://cdn.tailwindcss.com"></script>
  </head>
  <body>
    <a href="https://play.google.com/store/apps/details?id=com.acme">Google Play</a>
    <a href="https://apps.apple.com/app/id123">App Store</a>
    <p>Jane Founder is the Founder. Email jane@acme.example</p>
    <a href="mailto:hello@acme.example">Hello</a>
  </body>
</html>
"""


def make_profile(*, valid: bool = True, html: str = SAMPLE_HTML) -> WebsiteProfile:
    return WebsiteProfile(
        url="https://acme.example",
        final_url="https://acme.example/",
        title="Acme Labs",
        description="Acme builds modern workflow tools for startups worldwide.",
        status_code=200 if valid else 500,
        valid=valid,
        app_store_links=["https://apps.apple.com/app/id123"] if valid else [],
        play_store_links=(
            ["https://play.google.com/store/apps/details?id=com.acme"] if valid else []
        ),
        emails=["jane@acme.example", "hello@acme.example"] if valid else [],
        metadata={
            "html": html,
            "headers": {"server": "vercel"},
            "external_links": [
                "https://play.google.com/store/apps/details?id=com.acme",
                "https://apps.apple.com/app/id123",
            ],
            "internal_links": [],
        },
    )


@pytest.mark.asyncio
async def test_validation_pipeline_with_mocked_crawler() -> None:
    crawler = AsyncMock()
    crawler.analyze = AsyncMock(return_value=make_profile())
    pipeline = ValidationPipeline(crawler_service=crawler)

    report = await pipeline.run([StartupSeed(name="Acme Labs", website="https://acme.example")])

    assert report.summary.companies_processed == 1
    assert report.summary.reachable == 1
    result = report.results[0]
    assert result.website_reachable is True
    assert "Next.js" in result.technologies or "Tailwind" in result.technologies
    assert result.mobile_app is True
    assert result.app_store is True
    assert result.play_store is True
    assert result.contact_emails_found >= 1
    assert result.lead_intelligence is not None
    assert result.email_patterns is not None
    crawler.analyze.assert_awaited_once()


@pytest.mark.asyncio
async def test_validation_pipeline_unreachable_site() -> None:
    crawler = AsyncMock()
    crawler.analyze = AsyncMock(return_value=make_profile(valid=False, html=""))
    pipeline = ValidationPipeline(crawler_service=crawler)

    report = await pipeline.run([StartupSeed(name="Broken Co", website="https://broken.example")])

    result = report.results[0]
    assert result.website_reachable is False
    assert report.summary.reachable == 0


def test_compute_lead_score() -> None:
    score = compute_lead_score(
        qualification_score=65,
        contact_emails_found=2,
        technology_count=3,
        mobile_app=False,
        is_good_lead=True,
    )
    assert score == 88.0


def test_count_decision_makers() -> None:
    report = ContactDiscoveryReport(
        url="https://acme.example",
        contacts=[
            ContactCandidate(full_name="Jane", role="Founder", confidence=0.9),
            ContactCandidate(email="support@acme.example", role="Support", confidence=0.5),
        ],
        contact_count=2,
    )
    assert count_decision_makers(report) == 1


def test_render_report_contains_sections() -> None:
    report = ValidationReport(
        results=[
            CompanyValidationResult(
                name="Linear",
                website="linear.app",
                website_reachable=True,
                technologies=["React", "Next.js"],
                mobile_app=True,
                play_store=True,
                app_store=True,
                qualification_pass=True,
                qualification_score=92,
                contact_emails_found=3,
                decision_makers=2,
                email_pattern="firstname@linear.app",
                lead_score=94,
            )
        ],
        summary=ValidationSummary(
            companies_processed=1,
            reachable=1,
            qualified=1,
            mobile_apps=1,
            emails_found=3,
            technology_detection_success=1,
            average_lead_score=94.0,
            good_leads=1,
        ),
    )
    rendered = render_report(report)
    assert "Name:" in rendered
    assert "Linear" in rendered
    assert "Companies Processed:" in rendered
    assert "Average Lead Score:" in rendered


def test_load_startups_sample_file() -> None:
    path = Path(__file__).resolve().parents[1] / "sample_data" / "startups.json"
    startups = load_startups(path)
    assert len(startups) >= 20
    assert startups[0].name
    assert startups[0].website.startswith("http")
