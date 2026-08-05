from datetime import datetime, timezone

import pytest

from app.contact_discovery.types import ContactCandidate, ContactDiscoveryReport
from app.crawler.types import WebsiteProfile
from app.intelligence.builder import LeadIntelligenceBuilder
from app.intelligence.service import LeadIntelligenceService
from app.intelligence.types import PIPELINE_VERSION, LeadIntelligence
from app.mobile_detection.types import MobileAppDetectionResult
from app.qualification.types import QualificationResult
from app.schemas.company import CompanyResponse
from app.technology.types import Technology, TechnologyReport


def make_company(**overrides: object) -> CompanyResponse:
    payload = {
        "id": "company-1",
        "name": "Acme Labs",
        "website": "acme.example",
        "description": "Workflow tools",
        "industry": "SaaS",
        "source": "producthunt",
        "created_at": datetime.now(timezone.utc),
    }
    payload.update(overrides)
    return CompanyResponse(**payload)  # type: ignore[arg-type]


def make_good_lead_inputs() -> dict[str, object]:
    return {
        "company": make_company(),
        "website_profile": WebsiteProfile(
            url="https://acme.example",
            final_url="https://acme.example/",
            title="Acme",
            valid=True,
        ),
        "technology_report": TechnologyReport(
            url="https://acme.example",
            technologies=[
                Technology(name="Next.js", category="frontend", confidence=95, evidence=[]),
                Technology(name="Stripe", category="payment", confidence=90, evidence=[]),
            ],
            detected_count=2,
        ),
        "mobile_detection": MobileAppDetectionResult(
            has_mobile_app=False,
            confidence=0.0,
        ),
        "contact_discovery": ContactDiscoveryReport(
            url="https://acme.example",
            contacts=[
                ContactCandidate(
                    full_name="Jane Founder",
                    email="jane@acme.example",
                    role="Founder",
                    confidence=0.95,
                ),
                ContactCandidate(
                    email="support@acme.example",
                    role="Support",
                    confidence=0.55,
                ),
            ],
            emails=["jane@acme.example", "support@acme.example"],
            contact_count=2,
        ),
        "qualification": QualificationResult(
            qualified=True,
            score=65,
            level="Good",
            reasons=["Website exists"],
            warnings=[],
        ),
        "collector_name": "producthunt",
        "processing_time_ms": 123.4,
    }


def test_build_object() -> None:
    inputs = make_good_lead_inputs()
    intelligence = LeadIntelligenceService().build(**inputs)  # type: ignore[arg-type]

    assert isinstance(intelligence, LeadIntelligence)
    assert intelligence.company.name == "Acme Labs"
    assert intelligence.website_profile is not None
    assert intelligence.technology_report is not None
    assert intelligence.mobile_detection is not None
    assert intelligence.contact_discovery is not None
    assert intelligence.qualification is not None


def test_metadata() -> None:
    created_at = datetime(2024, 1, 15, tzinfo=timezone.utc)
    intelligence = (
        LeadIntelligenceBuilder()
        .with_company(make_company())
        .with_collector_name("producthunt")
        .with_processing_time_ms(42.5)
        .with_created_at(created_at)
        .build()
    )

    assert intelligence.metadata.collector_name == "producthunt"
    assert intelligence.metadata.processing_time_ms == 42.5
    assert intelligence.metadata.pipeline_version == PIPELINE_VERSION
    assert intelligence.metadata.created_at == created_at


def test_computed_properties() -> None:
    intelligence = LeadIntelligenceService().build(
        **make_good_lead_inputs()  # type: ignore[arg-type]
    )

    assert intelligence.has_mobile_app is False
    assert intelligence.qualification_score == 65
    assert intelligence.technology_names == ["Next.js", "Stripe"]
    assert intelligence.primary_email == "jane@acme.example"
    assert intelligence.primary_founder is not None
    assert intelligence.primary_founder.full_name == "Jane Founder"
    assert intelligence.best_contact is not None
    assert intelligence.best_contact.confidence == 0.95


def test_good_lead() -> None:
    intelligence = LeadIntelligenceService().build(
        **make_good_lead_inputs()  # type: ignore[arg-type]
    )
    assert intelligence.is_good_lead is True


def test_bad_lead_when_not_qualified() -> None:
    inputs = make_good_lead_inputs()
    inputs["qualification"] = QualificationResult(
        qualified=False,
        score=35,
        level="Poor",
        reasons=[],
        warnings=["Mobile app already exists"],
    )
    intelligence = LeadIntelligenceService().build(**inputs)  # type: ignore[arg-type]
    assert intelligence.is_good_lead is False


def test_bad_lead_with_mobile_app() -> None:
    inputs = make_good_lead_inputs()
    inputs["mobile_detection"] = MobileAppDetectionResult(
        has_mobile_app=True,
        confidence=0.95,
        android_detected=True,
    )
    # Scoring engine marks mobile apps unqualified; intelligence mirrors that flag.
    inputs["qualification"] = QualificationResult(
        qualified=False,
        score=40,
        level="Fair",
        reasons=[],
        warnings=["-25 Mobile app already exists"],
    )
    intelligence = LeadIntelligenceService().build(**inputs)  # type: ignore[arg-type]
    assert intelligence.is_good_lead is False
    assert intelligence.has_mobile_app is True


def test_no_contacts() -> None:
    inputs = make_good_lead_inputs()
    inputs["contact_discovery"] = ContactDiscoveryReport(
        url="https://acme.example",
        contacts=[],
        emails=[],
        contact_count=0,
    )
    intelligence = LeadIntelligenceService().build(**inputs)  # type: ignore[arg-type]
    assert intelligence.best_contact is None
    assert intelligence.primary_email is None
    assert intelligence.primary_founder is None
    # is_good_lead follows qualification.qualified only (Good/Excellent).
    assert intelligence.is_good_lead is True


def test_technology_list() -> None:
    intelligence = LeadIntelligenceService().build(
        **make_good_lead_inputs()  # type: ignore[arg-type]
    )
    assert "Next.js" in intelligence.technology_names
    assert "Stripe" in intelligence.technology_names


def test_primary_email() -> None:
    intelligence = LeadIntelligenceService().build(
        **make_good_lead_inputs()  # type: ignore[arg-type]
    )
    assert intelligence.primary_email == "jane@acme.example"


def test_primary_founder() -> None:
    intelligence = LeadIntelligenceService().build(
        **make_good_lead_inputs()  # type: ignore[arg-type]
    )
    founder = intelligence.primary_founder
    assert founder is not None
    assert founder.role == "Founder"


def test_builder_requires_company() -> None:
    with pytest.raises(ValueError, match="company is required"):
        LeadIntelligenceBuilder().build()
