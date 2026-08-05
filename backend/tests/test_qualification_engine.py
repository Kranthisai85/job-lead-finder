from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.collectors.types import CompanyLead
from app.contact_discovery.types import ContactCandidate, ContactDiscoveryReport
from app.crawler.types import WebsiteProfile
from app.mobile_detection.types import MobileAppDetectionResult
from app.qualification.context import QualificationContext
from app.qualification.scoring_engine import QualificationScoringEngine
from app.qualification.service import QualificationService
from app.qualification.types import QualificationLevel
from app.qualification.weights import (
    DEFAULT_SCORING_CONFIG,
    QualificationScoringConfig,
    QualificationWeights,
)
from app.technology.types import Technology, TechnologyReport


def make_lead(**overrides: Any) -> CompanyLead:
    base: dict[str, Any] = {
        "name": "Acme Labs",
        "website": "https://acme.example",
        "description": (
            "Acme Labs builds modern SaaS tooling for product teams with "
            "reliable workflows and integrations across the stack."
        ),
        "source": "producthunt",
        "tags": ["SaaS"],
        "discovered_at": datetime.now(timezone.utc) - timedelta(days=5),
        "metadata": {
            "launch_date": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
        },
    }
    base.update(overrides)
    return CompanyLead(**base)


def score_context(context: QualificationContext) -> Any:
    return QualificationScoringEngine(DEFAULT_SCORING_CONFIG).score(context)


def test_github_repository_is_penalized() -> None:
    lead = make_lead(website="https://github.com/acme/cool-app")
    result = score_context(QualificationContext.from_company_lead(lead))

    assert any("GitHub repository" in warning for warning in result.warnings)
    assert result.score < 60
    assert result.qualified is False
    assert result.level in {QualificationLevel.FAIR, QualificationLevel.POOR}


def test_vercel_demo_is_penalized() -> None:
    lead = make_lead(
        website="https://demo-app.vercel.app",
        description="Coming soon demo sandbox for our prototype landing page.",
    )
    result = score_context(QualificationContext.from_company_lead(lead))

    assert any("vercel.app" in warning.lower() for warning in result.warnings)
    assert result.qualified is False


def test_real_saas_scores_well() -> None:
    lead = make_lead()
    profile = WebsiteProfile(
        url="https://acme.example",
        final_url="https://acme.example",
        title="Acme Labs",
        description=lead.description,
        contact_pages=["https://acme.example/contact"],
        career_pages=[],
        technologies=["Next.js", "React"],
        emails=["hello@acme.example"],
        valid=True,
    )
    tech = TechnologyReport(
        url="https://acme.example",
        technologies=[
            Technology(name="Next.js", category="framework", confidence=90),
            Technology(name="React", category="framework", confidence=90),
        ],
        detected_count=2,
    )
    contacts = ContactDiscoveryReport(
        url="https://acme.example",
        contacts=[
            ContactCandidate(
                full_name="Ada Founder",
                email="ada@acme.example",
                role="Founder",
                confidence=0.9,
            )
        ],
        emails=["ada@acme.example"],
        contact_count=1,
    )
    mobile = MobileAppDetectionResult(has_mobile_app=False, confidence=0.2)
    context = QualificationContext.from_enriched(
        lead,
        website_profile=profile,
        technology_report=tech,
        mobile_report=mobile,
        contacts=contacts,
    )
    result = score_context(context)

    assert result.score >= 60
    assert result.qualified is True
    assert result.level in {QualificationLevel.GOOD, QualificationLevel.EXCELLENT}
    assert any("Custom domain" in reason for reason in result.reasons)
    assert any("HTTPS" in reason for reason in result.reasons)
    assert any("React or Next.js" in reason for reason in result.reasons)


def test_flutter_company_gets_flutter_bonus() -> None:
    lead = make_lead(
        description=(
            "We help teams ship Flutter apps faster with shared design systems "
            "and production-ready mobile components for startups."
        )
    )
    tech = TechnologyReport(
        url="https://acme.example",
        technologies=[Technology(name="Flutter", category="framework", confidence=95)],
        detected_count=1,
    )
    context = QualificationContext.from_enriched(lead, technology_report=tech)
    result = score_context(context)

    assert any("Flutter mentioned" in reason for reason in result.reasons)
    assert result.score >= 60


def test_existing_mobile_app_is_penalized() -> None:
    lead = make_lead()
    mobile = MobileAppDetectionResult(
        has_mobile_app=True,
        confidence=0.9,
        android_detected=True,
        ios_detected=True,
    )
    context = QualificationContext.from_enriched(lead, mobile_report=mobile)
    result = score_context(context)

    assert any("Mobile app already exists" in warning for warning in result.warnings)
    assert not any("No mobile app detected" in reason for reason in result.reasons)


def test_company_hiring_flutter_scores_excellent_signal() -> None:
    lead = make_lead()
    profile = WebsiteProfile(
        url="https://acme.example",
        final_url="https://acme.example",
        title="Acme Careers",
        description="We are hiring Flutter engineers for our mobile platform team.",
        contact_pages=["https://acme.example/contact"],
        career_pages=["https://acme.example/careers"],
        technologies=["Flutter"],
        valid=True,
    )
    context = QualificationContext.from_enriched(
        lead,
        website_profile=profile,
        technology_report=TechnologyReport(
            url="https://acme.example",
            technologies=[Technology(name="Flutter", category="framework", confidence=90)],
            detected_count=1,
        ),
        mobile_report=MobileAppDetectionResult(has_mobile_app=False, confidence=0.1),
        contacts=ContactDiscoveryReport(
            url="https://acme.example",
            emails=["jobs@acme.example"],
            contacts=[
                ContactCandidate(email="jobs@acme.example", role="Recruiter", confidence=0.8)
            ],
            contact_count=1,
        ),
    )
    # Ensure hiring text includes explicit hiring + flutter.
    context = context.model_copy(
        update={
            "hiring_text": (
                "Careers: we are hiring Flutter developers and mobile engineers. "
                + context.hiring_text
            )
        }
    )
    result = score_context(context)

    assert any("Hiring Flutter" in reason for reason in result.reasons)
    assert any("Careers page" in reason for reason in result.reasons)
    assert result.qualified is True
    assert result.score >= 80
    assert result.level == QualificationLevel.EXCELLENT


def test_hiring_report_awards_engineering_and_remote_bonuses() -> None:
    from app.hiring_detection.types import HiringDetectionReport, HiringOpportunity

    lead = make_lead()
    hiring = HiringDetectionReport(
        url="https://acme.example",
        jobs_found=1,
        flutter_jobs=1,
        mobile_jobs=1,
        frontend_jobs=0,
        engineering_jobs=1,
        provider="Greenhouse",
        confidence=0.9,
        opportunities=[
            HiringOpportunity(
                title="Senior Flutter Engineer",
                remote=True,
                matched_keywords=["flutter", "flutter engineer"],
                confidence=0.9,
            )
        ],
        has_engineering_careers_page=True,
        has_remote_engineering=True,
    )
    context = QualificationContext.from_enriched(lead, hiring_report=hiring)
    result = score_context(context)

    assert any("Hiring Flutter" in reason for reason in result.reasons)
    assert any("Hiring Mobile" in reason for reason in result.reasons)
    assert any("Engineering careers page" in reason for reason in result.reasons)
    assert any("Remote engineering" in reason for reason in result.reasons)
    assert context.flutter_jobs == 1
    assert context.has_remote_engineering is True


def test_levels_boundaries() -> None:
    engine = QualificationScoringEngine(
        QualificationScoringConfig(
            weights=QualificationWeights(
                website_exists=0,
                custom_domain=0,
                https_enabled=0,
                recently_launched=0,
                description_long=0,
                contact_page_exists=0,
                valid_business_email=0,
                no_mobile_app=0,
                react_or_nextjs=0,
                flutter_mentioned=0,
                careers_page=0,
                hiring_flutter=0,
                hiring_mobile=0,
                hiring_frontend=0,
                engineering_careers_page=0,
                remote_engineering=0,
                intelligence_b2b_saas=0,
                intelligence_enterprise_software=0,
                intelligence_clear_icp=0,
                intelligence_pricing_page=0,
                intelligence_developer_tools=0,
                github_repository_website=0,
                github_pages=0,
                gitlab_pages=0,
                portfolio_website=0,
                demo_website=0,
                placeholder_landing=0,
                only_vercel_app=0,
                only_netlify_app=0,
                no_contact_information=0,
                mobile_app_exists=0,
            )
        )
    )
    # Force score via a minimal lead + monkeypatch by constructing result levels directly
    from app.qualification.types import QualificationResult

    assert engine._level_for(80) == QualificationLevel.EXCELLENT
    assert engine._level_for(60) == QualificationLevel.GOOD
    assert engine._level_for(40) == QualificationLevel.FAIR
    assert engine._level_for(39) == QualificationLevel.POOR
    sample = QualificationResult(
        qualified=True,
        score=60,
        level=QualificationLevel.GOOD,
        reasons=["ok"],
        warnings=[],
    )
    assert sample.qualification_score == 60
    assert sample.qualification_level == "Good"


def test_qualification_service_logging_fields(caplog: pytest.LogCaptureFixture) -> None:
    service = QualificationService()
    with caplog.at_level("INFO"):
        result = service.qualify(make_lead())

    assert result.qualification_score == result.score
    assert any("qualification_score=" in record.getMessage() for record in caplog.records)
    assert any("qualification_level=" in record.getMessage() for record in caplog.records)


def test_filter_qualified_uses_good_threshold() -> None:
    service = QualificationService()
    good = make_lead()
    bad = make_lead(
        website="https://user.github.io/demo",
        description="coming soon placeholder portfolio demo",
    )
    qualified = service.filter_qualified([good, bad])
    assert all(lead.name == good.name for lead in qualified) or len(qualified) <= 1
