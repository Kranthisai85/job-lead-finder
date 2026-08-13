from __future__ import annotations

from datetime import datetime, timezone

from app.company_profile.types import CompanyProfile
from app.contact_discovery.types import ContactCandidate, ContactDiscoveryReport
from app.crawler.types import WebsiteProfile
from app.hiring_detection.types import HiringDetectionReport, HiringOpportunity
from app.intelligence.types import LeadIntelligence, LeadIntelligenceMetadata
from app.mobile_detection.types import MobileAppDetectionResult
from app.personalization.service import CompanyPersonalizationService
from app.pipeline.types import CompleteLead, ProcessingMetadata, StartupSeed
from app.qualification.types import QualificationResult
from app.schemas.company import CompanyResponse
from app.technology.types import Technology, TechnologyReport


def make_lead(
    *,
    has_mobile_app: bool = False,
    android: bool = False,
    ios: bool = False,
    technologies: list[str] | None = None,
    with_contacts: bool = True,
    qualified: bool = True,
    qualification_score: int = 80,
    include_mobile_report: bool = True,
    include_qualification: bool = True,
    include_intelligence: bool = True,
    company_name: str = "Acme",
    description: str | None = None,
    html: str | None = None,
    hiring_report: HiringDetectionReport | None = None,
) -> CompleteLead:
    tech_names = technologies if technologies is not None else ["React", "Tailwind"]
    technology_report = None
    if tech_names:
        technology_report = TechnologyReport(
            url="https://acme.example/",
            technologies=[
                Technology(name=name, category="frontend", confidence=90) for name in tech_names
            ],
            detected_count=len(tech_names),
        )

    contacts = None
    if with_contacts:
        contacts = ContactDiscoveryReport(
            url="https://acme.example/",
            contacts=[
                ContactCandidate(
                    full_name="Ada Lovelace",
                    first_name="Ada",
                    last_name="Lovelace",
                    email="ada@acme.example",
                    role="founder",
                    confidence=0.9,
                )
            ],
            emails=["ada@acme.example"],
            contact_count=1,
        )

    qualification = None
    if include_qualification:
        qualification = QualificationResult(
            qualified=qualified,
            score=qualification_score,
            reasons=["website present", "description exists"],
        )

    mobile_report = None
    if include_mobile_report:
        mobile_report = MobileAppDetectionResult(
            has_mobile_app=has_mobile_app,
            confidence=0.9 if has_mobile_app else 0.1,
            android_detected=android,
            ios_detected=ios,
        )

    company_description = description or "Issue tracking for software teams"
    metadata = {"html": html} if html else {}

    intelligence = None
    if include_intelligence:
        intelligence = LeadIntelligence(
            company=CompanyResponse(
                id="1",
                name=company_name,
                website="acme.example",
                description=company_description,
                industry="Project Management",
                source="test",
                created_at=datetime.now(timezone.utc),
            ),
            website_profile=WebsiteProfile(
                url="https://acme.example",
                final_url="https://acme.example/",
                title=company_name,
                valid=True,
                status_code=200,
                metadata=metadata,
            ),
            technology_report=technology_report,
            mobile_detection=mobile_report,
            contact_discovery=contacts,
            qualification=qualification,
            metadata=LeadIntelligenceMetadata(collector_name="test"),
        )

    return CompleteLead(
        startup=StartupSeed(
            name=company_name,
            website="https://acme.example",
            description=company_description,
            source="test",
        ),
        website_profile=WebsiteProfile(
            url="https://acme.example",
            final_url="https://acme.example/",
            title=company_name,
            description=company_description,
            valid=True,
            status_code=200,
            metadata=metadata,
        ),
        company_profile=CompanyProfile(
            company_name=company_name,
            short_description=company_description,
            business_category="Developer Tools",
            industry="Project Management",
            product_type="SaaS",
            target_audience="Developers",
            confidence=0.8,
        ),
        technology_report=technology_report,
        mobile_report=mobile_report,
        qualification_report=qualification,
        contacts=contacts,
        hiring_report=hiring_report,
        lead_intelligence=intelligence,
        processing=ProcessingMetadata(success=True),
    )


def test_no_mobile_app_opportunity() -> None:
    context = CompanyPersonalizationService().generate(make_lead(has_mobile_app=False))
    assert context.has_mobile_app is False
    assert "curious whether" in context.mobile_app_opportunity
    assert "mobile is already on your roadmap" in context.mobile_app_opportunity
    assert "React" not in context.personalized_opening
    assert "Tailwind" not in context.personalized_opening
    assert "Acme" in context.personalized_opening
    assert "Detected stack" not in context.technologies_summary or "Internal" in (
        context.technologies_summary
    )


def test_mobile_app_detected() -> None:
    context = CompanyPersonalizationService().generate(
        make_lead(has_mobile_app=True, android=True, ios=True)
    )
    assert context.has_mobile_app is True
    assert "already appears to offer a mobile presence" in context.mobile_app_opportunity
    assert "Google Play" in context.mobile_app_opportunity
    assert "App Store" in context.mobile_app_opportunity
    assert any("Mobile app already detected" in warning for warning in context.warnings)


def test_flutter_technology_is_flutter_lead() -> None:
    context = CompanyPersonalizationService().generate(
        make_lead(technologies=["Flutter", "Firebase"], has_mobile_app=False)
    )
    assert context.is_flutter_lead is True
    assert "Flutter" in context.suggested_value_proposition
    assert "technical partnership" not in context.suggested_value_proposition.lower()


def test_dart_technology_is_flutter_lead() -> None:
    context = CompanyPersonalizationService().generate(
        make_lead(technologies=["Dart"], has_mobile_app=False)
    )
    assert context.is_flutter_lead is True


def test_website_flutter_developer_copy_is_flutter_lead() -> None:
    context = CompanyPersonalizationService().generate(
        make_lead(
            technologies=["React"],
            description="We are hiring a Flutter developer for our mobile roadmap.",
        )
    )
    assert context.is_flutter_lead is True


def test_hiring_flutter_job_is_flutter_lead() -> None:
    hiring = HiringDetectionReport(
        url="https://acme.example",
        jobs_found=1,
        flutter_jobs=1,
        opportunities=[
            HiringOpportunity(
                title="Senior Flutter Engineer",
                matched_keywords=["flutter"],
                confidence=0.9,
            )
        ],
    )
    context = CompanyPersonalizationService().generate(
        make_lead(technologies=["React", "Vercel"], hiring_report=hiring)
    )
    assert context.is_flutter_lead is True


def test_react_vue_svelte_only_is_not_flutter_lead() -> None:
    context = CompanyPersonalizationService().generate(
        make_lead(
            technologies=["Vercel", "Nuxt", "Cloudflare", "Vue", "Svelte", "React"],
            has_mobile_app=False,
            qualified=True,
            with_contacts=True,
        )
    )
    assert context.is_flutter_lead is False
    assert "technical partnership" not in context.suggested_value_proposition.lower()
    assert context.outreach_mode == "freelance"
    assert "freelance" in context.suggested_value_proposition.lower()
    assert "Flutter" in context.suggested_value_proposition


def test_no_mobile_app_does_not_imply_flutter() -> None:
    context = CompanyPersonalizationService().generate(
        make_lead(
            technologies=["Netlify", "Google Analytics"],
            has_mobile_app=False,
            qualified=True,
            with_contacts=True,
        )
    )
    assert context.has_mobile_app is False
    assert context.is_flutter_lead is False


def test_no_flutter_evidence_is_not_flutter_lead() -> None:
    context = CompanyPersonalizationService().generate(
        make_lead(technologies=["Vercel"], has_mobile_app=False, qualified=True)
    )
    assert context.is_flutter_lead is False


def test_non_flutter_lead_with_mobile() -> None:
    context = CompanyPersonalizationService().generate(
        make_lead(has_mobile_app=True, qualified=True, with_contacts=True)
    )
    assert context.is_flutter_lead is False
    assert "Flutter" in context.suggested_value_proposition


def test_missing_technologies() -> None:
    context = CompanyPersonalizationService().generate(make_lead(technologies=[]))
    assert context.technologies_summary == (
        "No clear technology signals were detected on the website."
    )
    assert "Missing technology signals" in context.warnings
    assert "Acme" in context.personalized_opening
    assert "built with" not in context.personalized_opening.lower()


def test_missing_contacts() -> None:
    context = CompanyPersonalizationService().generate(make_lead(with_contacts=False))
    assert "Missing contacts" in context.warnings
    assert context.is_flutter_lead is False
    assert "flutter" in context.cta_recommendation.lower() or "mobile" in (
        context.cta_recommendation.lower()
    )


def test_strips_tagline_from_company_name() -> None:
    lead = make_lead(
        company_name="Pesterly: somebody has to nag. It doesn't have to be you."
    )
    lead.startup.name = "Pesterly"
    context = CompanyPersonalizationService().generate(lead)
    assert context.company_name == "Pesterly"
    assert "somebody has to nag" not in context.company_name
    assert "somebody has to nag" not in context.personalized_opening


def test_confidence_scoring() -> None:
    rich = CompanyPersonalizationService().generate(make_lead())
    sparse = CompanyPersonalizationService().generate(
        make_lead(
            technologies=[],
            with_contacts=False,
            include_qualification=False,
            include_mobile_report=False,
            include_intelligence=False,
        )
    )
    assert rich.confidence_score > sparse.confidence_score
    assert 0.0 <= sparse.confidence_score <= 1.0
    assert 0.0 <= rich.confidence_score <= 1.0


def test_warning_generation() -> None:
    lead = make_lead(
        technologies=[],
        with_contacts=False,
        include_qualification=False,
        include_mobile_report=False,
        include_intelligence=False,
        has_mobile_app=False,
    )
    lead.processing.errors.append("crawler failed: timeout")
    context = CompanyPersonalizationService().generate(lead)
    assert "Missing technology signals" in context.warnings
    assert "Missing contacts" in context.warnings
    assert "Missing qualification data" in context.warnings
    assert "Pipeline reported processing errors" in context.warnings


def test_company_summary_and_qualification() -> None:
    context = CompanyPersonalizationService().generate(make_lead())
    assert "Acme" in context.company_summary
    assert "Developer Tools" in context.company_summary or "Project Management" in (
        context.company_summary
    )
    assert "Qualification passed" in context.qualification_summary
    assert "80/100" in context.qualification_summary
