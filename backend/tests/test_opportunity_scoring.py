from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.company_intelligence.models import CompanyIntelligenceReport
from app.company_profile.types import CompanyProfile
from app.contact_discovery.types import (
    CompanyDecisionMaker,
    ContactCandidate,
    ContactDiscoveryReport,
)
from app.crawler.types import WebsiteProfile
from app.hiring_detection.types import HiringDetectionReport, HiringOpportunity
from app.mobile_detection.types import MobileAppDetectionResult
from app.opportunity_scoring.service import OpportunityScoringService
from app.opportunity_scoring.weights import (
    DEFAULT_WEIGHTS,
    OpportunityScoringConfig,
    OpportunityWeights,
)
from app.technology.types import Technology, TechnologyReport


def make_profile(
    *,
    url: str = "https://acme.example",
    html: str = "<html><head><meta name='viewport' content='width=device-width'></head></html>",
    pricing_pages: list[str] | None = None,
    technologies: list[str] | None = None,
    app_store: list[str] | None = None,
    play_store: list[str] | None = None,
) -> WebsiteProfile:
    return WebsiteProfile(
        url=url,
        final_url=f"{url.rstrip('/')}/",
        title="Acme",
        description="B2B SaaS platform",
        pricing_pages=pricing_pages or [],
        technologies=technologies or [],
        app_store_links=app_store or [],
        play_store_links=play_store or [],
        metadata={"html": html},
        valid=True,
    )


def score(**kwargs: object):
    return OpportunityScoringService().score(**kwargs)  # type: ignore[arg-type]


def test_weights_live_only_in_weights_module() -> None:
    assert DEFAULT_WEIGHTS.flutter_hiring == 40
    assert DEFAULT_WEIGHTS.no_mobile_app == 12
    assert DEFAULT_WEIGHTS.product_hunt == 5
    assert DEFAULT_WEIGHTS.flutter_already_detected < 0
    assert DEFAULT_WEIGHTS.existing_native_apps < 0
    assert DEFAULT_WEIGHTS.non_company_website < 0


def test_no_mobile_app_and_flutter_hiring_is_hot() -> None:
    report = score(
        url="https://acme.example",
        website_profile=make_profile(technologies=["React", "Next.js"]),
        mobile_report=MobileAppDetectionResult(has_mobile_app=False, confidence=0.2),
        hiring_report=HiringDetectionReport(
            url="https://acme.example",
            jobs_found=2,
            flutter_jobs=1,
            mobile_jobs=1,
            frontend_jobs=1,
            opportunities=[
                HiringOpportunity(title="Flutter Engineer", matched_keywords=["flutter"])
            ],
        ),
        company_intelligence=CompanyIntelligenceReport(
            url="https://acme.example",
            is_b2b_saas=True,
            is_developer_tools=True,
            has_pricing_page=True,
            company_stage="Early Startup",
            confidence=0.8,
        ),
        technology_report=TechnologyReport(
            url="https://acme.example",
            technologies=[
                Technology(name="React", category="framework", confidence=90),
                Technology(name="Next.js", category="framework", confidence=90),
            ],
            detected_count=2,
        ),
        contacts=ContactDiscoveryReport(
            url="https://acme.example",
            decision_makers=[
                CompanyDecisionMaker(
                    name="Jane Founder",
                    role="Founder",
                    email="jane@acme.example",
                    confidence=0.9,
                    contact_score=100,
                )
            ],
            decision_makers_found=1,
            contacts=[
                ContactCandidate(
                    full_name="Jane Founder",
                    role="Founder",
                    email="jane@acme.example",
                    confidence=0.9,
                )
            ],
            contact_count=1,
        ),
        source="producthunt",
        launch_date=datetime.now(timezone.utc) - timedelta(days=5),
        description="Y Combinator backed SaaS launched on Product Hunt. Raised Series A.",
    )

    assert report.overall_score >= 85
    assert report.priority == "Critical"
    assert report.opportunity_level == "Exceptional"
    assert report.recommended_action == "Send immediately"
    assert "flutter_hiring" in report.score_breakdown
    assert "no_mobile_app" in report.score_breakdown
    assert "founder_email" in report.score_breakdown
    assert 0.0 <= report.confidence <= 1.0


def test_existing_flutter_app_is_penalized() -> None:
    report = score(
        url="https://done.example",
        website_profile=make_profile(
            technologies=["Flutter"],
            app_store=["https://apps.apple.com/app/id1"],
        ),
        mobile_report=MobileAppDetectionResult(
            has_mobile_app=True,
            confidence=0.9,
            ios_detected=True,
            evidence=["flutter app"],
        ),
        technology_report=TechnologyReport(
            url="https://done.example",
            technologies=[Technology(name="Flutter", category="framework", confidence=95)],
            detected_count=1,
        ),
    )
    assert report.score_breakdown.get("flutter_already_detected", 0) < 0
    assert report.score_breakdown.get("existing_native_apps", 0) < 0
    assert report.priority in {"Low", "Very Low", "Medium"}
    assert any("Flutter already" in w for w in report.warnings)


def test_consumer_low_priority_without_hiring() -> None:
    report = score(
        url="https://fun.example",
        website_profile=make_profile(),
        mobile_report=MobileAppDetectionResult(has_mobile_app=True, confidence=0.8),
        company_intelligence=CompanyIntelligenceReport(
            url="https://fun.example",
            is_consumer_only=True,
            is_b2b_saas=False,
            business_model="Consumer App",
            target_customer="B2C",
            confidence=0.5,
        ),
    )
    assert report.overall_score < 50
    assert report.recommended_action in {"Wait", "Ignore", "Research manually"}


def test_founder_email_recommends_send_founder_email_on_high() -> None:
    # Tune weights so score lands in High band with founder email.
    config = OpportunityScoringConfig(
        max_contact_points=50,
        weights=OpportunityWeights(
            no_mobile_app=30,
            founder_email=25,
            founder_contact=20,
            decision_maker_found=0,
            flutter_hiring=0,
            mobile_hiring=0,
            frontend_hiring=0,
            developer_tools=0,
            b2b_saas=0,
            enterprise=0,
            pricing_page=0,
            company_age_young=0,
            early_startup=0,
            growth_startup=0,
            recently_launched=0,
            product_hunt=0,
            yc=0,
            funding_news=0,
            recent_hiring=0,
            technology_fit=0,
            react_website=0,
            nextjs=0,
            pwa=0,
            responsive_only=0,
            react_native_detected=0,
            flutter_already_detected=0,
            existing_native_apps=0,
            non_company_website=0,
        ),
    )
    report = OpportunityScoringService(config=config).score(
        url="https://acme.example",
        mobile_report=MobileAppDetectionResult(has_mobile_app=False, confidence=0.2),
        contacts=ContactDiscoveryReport(
            url="https://acme.example",
            decision_makers=[
                CompanyDecisionMaker(
                    name="Ada",
                    role="CEO",
                    email="ada@acme.example",
                    confidence=0.9,
                )
            ],
            decision_makers_found=1,
            contact_count=1,
        ),
    )
    assert report.priority == "High"
    assert report.recommended_action == "Send founder email"


def test_priority_bands() -> None:
    service = OpportunityScoringService()
    no_hiring = type("Ctx", (), {"hiring_report": None})()
    with_hiring = type(
        "Ctx",
        (),
        {
            "hiring_report": HiringDetectionReport(
                url="https://acme.example",
                jobs_found=1,
                flutter_jobs=1,
                mobile_jobs=0,
            )
        },
    )()
    assert service._priority_for(90, with_hiring) == "Critical"
    assert service._priority_for(90, no_hiring) == "High"
    assert service._priority_for(75, no_hiring) == "High"
    assert service._priority_for(55, no_hiring) == "Medium"
    assert service._priority_for(35, no_hiring) == "Low"
    assert service._priority_for(10, no_hiring) == "Very Low"


def test_soft_stack_without_hiring_is_not_critical() -> None:
    report = score(
        url="https://acme.example",
        source="producthunt",
        mobile_report=MobileAppDetectionResult(has_mobile_app=False, confidence=0.2),
        contacts=ContactDiscoveryReport(
            url="https://acme.example",
            decision_makers=[
                CompanyDecisionMaker(
                    name="Jane Founder",
                    role="Founder",
                    email="jane@acme.example",
                    confidence=0.9,
                    contact_score=100,
                )
            ],
            decision_makers_found=1,
            contact_count=1,
        ),
        launch_date=datetime.now(timezone.utc) - timedelta(days=5),
    )
    assert report.priority != "Critical"
    assert report.overall_score < 100


def test_non_company_website_is_penalized() -> None:
    report = score(url="https://www.producthunt.com/r/ABC")
    assert report.score_breakdown.get("non_company_website", 0) < 0
    assert report.overall_score <= 40
    assert report.priority in {"Low", "Very Low", "Medium"}


def test_recommended_actions_mapping() -> None:
    assert (
        OpportunityScoringService._recommended_action("Critical", has_founder_email=False)
        == "Send immediately"
    )
    assert (
        OpportunityScoringService._recommended_action("High", has_founder_email=True)
        == "Send founder email"
    )
    assert (
        OpportunityScoringService._recommended_action("Medium", has_founder_email=False)
        == "Research manually"
    )
    assert OpportunityScoringService._recommended_action("Low", has_founder_email=False) == "Wait"
    assert (
        OpportunityScoringService._recommended_action("Very Low", has_founder_email=False)
        == "Ignore"
    )


def test_react_next_pwa_signals() -> None:
    report = score(
        url="https://web.example",
        website_profile=make_profile(technologies=["React", "PWA"]),
        technology_report=TechnologyReport(
            url="https://web.example",
            technologies=[
                Technology(name="React", category="framework", confidence=90),
                Technology(name="Next.js", category="framework", confidence=90),
                Technology(name="PWA", category="capability", confidence=70),
            ],
            detected_count=3,
        ),
        mobile_report=MobileAppDetectionResult(has_mobile_app=False, confidence=0.2),
    )
    assert "react_website" in report.score_breakdown
    assert "nextjs" in report.score_breakdown
    assert "pwa" in report.score_breakdown
    assert "technology_fit" in report.score_breakdown
    assert "responsive_only" in report.score_breakdown


def test_react_native_detected() -> None:
    report = score(
        url="https://rn.example",
        technology_report=TechnologyReport(
            url="https://rn.example",
            technologies=[Technology(name="React Native", category="framework", confidence=90)],
            detected_count=1,
        ),
    )
    assert "react_native_detected" in report.score_breakdown


def test_yc_product_hunt_funding() -> None:
    report = score(
        url="https://startup.example",
        source="producthunt",
        description="Y Combinator W24 batch. We raised a seed round.",
        company_intelligence=CompanyIntelligenceReport(
            url="https://startup.example",
            funding_status="Seed",
            company_stage="Growth",
            confidence=0.7,
        ),
    )
    assert "product_hunt" in report.score_breakdown
    assert "yc" in report.score_breakdown
    assert "funding_news" in report.score_breakdown
    assert "growth_startup" in report.score_breakdown


def test_company_age_young() -> None:
    current = datetime.now(timezone.utc).year
    report = score(
        url="https://young.example",
        company_profile=CompanyProfile(
            company_name="YoungCo",
            founded_year=current - 2,
            source_url="https://young.example",
            confidence=0.5,
        ),
    )
    assert "company_age_young" in report.score_breakdown


def test_score_breakdown_sums_toward_overall() -> None:
    report = score(
        url="https://acme.example",
        mobile_report=MobileAppDetectionResult(has_mobile_app=False, confidence=0.2),
        hiring_report=HiringDetectionReport(
            url="https://acme.example",
            jobs_found=1,
            flutter_jobs=1,
        ),
    )
    raw = sum(report.score_breakdown.values())
    assert report.overall_score == max(0, min(100, raw))


def test_logging_fields(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO"):
        score(
            url="https://acme.example",
            mobile_report=MobileAppDetectionResult(has_mobile_app=False, confidence=0.2),
        )
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "overall_score=" in messages
    assert "priority=" in messages
    assert "recommended_action=" in messages
    assert "confidence=" in messages


def test_ignore_when_very_low() -> None:
    config = OpportunityScoringConfig(
        weights=OpportunityWeights(
            no_mobile_app=0,
            flutter_hiring=0,
            mobile_hiring=0,
            frontend_hiring=0,
            developer_tools=0,
            b2b_saas=0,
            enterprise=0,
            pricing_page=0,
            founder_contact=0,
            decision_maker_found=0,
            founder_email=0,
            company_age_young=0,
            early_startup=0,
            growth_startup=0,
            recently_launched=0,
            product_hunt=0,
            yc=0,
            funding_news=0,
            recent_hiring=0,
            technology_fit=0,
            react_website=0,
            nextjs=0,
            pwa=0,
            responsive_only=0,
            react_native_detected=0,
            flutter_already_detected=0,
            existing_native_apps=0,
            non_company_website=0,
        )
    )
    report = OpportunityScoringService(config=config).score(url="https://empty.example")
    assert report.overall_score == 0
    assert report.priority == "Very Low"
    assert report.recommended_action == "Ignore"
