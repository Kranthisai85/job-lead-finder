from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.company_profile.types import CompanyProfile
from app.contact_discovery.types import ContactCandidate, ContactDiscoveryReport
from app.crawler.types import WebsiteProfile
from app.email_patterns.types import EmailPattern, EmailPatternReport
from app.intelligence.types import LeadIntelligence, LeadIntelligenceMetadata
from app.mobile_detection.types import MobileAppDetectionResult
from app.pipeline.processor import LeadProcessor
from app.pipeline.service import LeadPipelineService
from app.pipeline.types import StartupSeed
from app.qualification.types import QualificationResult
from app.schemas.company import CompanyResponse
from app.technology.types import Technology, TechnologyReport


def make_startup() -> StartupSeed:
    return StartupSeed(
        name="Acme",
        website="https://acme.example",
        description="Issue tracking for software teams",
        source="test",
    )


def make_profile() -> WebsiteProfile:
    return WebsiteProfile(
        url="https://acme.example",
        final_url="https://acme.example/",
        title="Acme",
        description="Issue tracking for software teams",
        valid=True,
        status_code=200,
        metadata={"html": "<html><title>Acme</title></html>", "headers": {}},
    )


def make_company_profile() -> CompanyProfile:
    return CompanyProfile(
        company_name="Acme",
        tagline="Issue tracking for software teams",
        short_description="Issue tracking for software teams",
        business_category="Developer Tools",
        industry="Project Management",
        product_type="SaaS",
        target_audience="Developers",
        pricing_model="Freemium",
        primary_cta="Start Free",
        source_url="https://acme.example/",
        confidence=0.8,
    )


def make_technology_report() -> TechnologyReport:
    return TechnologyReport(
        url="https://acme.example/",
        technologies=[Technology(name="React", category="frontend", confidence=90)],
        detected_count=1,
    )


def make_mobile_report() -> MobileAppDetectionResult:
    return MobileAppDetectionResult(has_mobile_app=False, confidence=0.1)


def make_qualification() -> QualificationResult:
    return QualificationResult(qualified=True, score=80, reasons=["website present"])


def make_contacts() -> ContactDiscoveryReport:
    return ContactDiscoveryReport(
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


def make_email_patterns() -> EmailPatternReport:
    return EmailPatternReport(
        domain="acme.example",
        patterns=[
            EmailPattern(
                pattern_name="first",
                template="{first}@{domain}",
                confidence=0.8,
                generated_addresses=["ada@acme.example"],
            )
        ],
        candidates=["ada@acme.example"],
        inferred_pattern="{first}",
        confidence=0.8,
    )


def make_intelligence() -> LeadIntelligence:
    return LeadIntelligence(
        company=CompanyResponse(
            id="1",
            name="Acme",
            website="acme.example",
            description="Issue tracking",
            industry="Project Management",
            source="test",
            created_at=datetime.now(timezone.utc),
        ),
        website_profile=make_profile(),
        technology_report=make_technology_report(),
        mobile_detection=make_mobile_report(),
        contact_discovery=make_contacts(),
        qualification=make_qualification(),
        metadata=LeadIntelligenceMetadata(collector_name="test", processing_time_ms=12.0),
    )


def build_processor(**overrides: Any) -> LeadProcessor:
    crawler = AsyncMock()
    crawler.analyze = AsyncMock(return_value=make_profile())

    company_profile = MagicMock()
    company_profile.extract.return_value = make_company_profile()

    technology = MagicMock()
    technology.detect.return_value = make_technology_report()

    mobile = MagicMock()
    mobile.detect.return_value = make_mobile_report()

    qualification = MagicMock()
    qualification.qualify.return_value = make_qualification()

    contacts = MagicMock()
    contacts.discover.return_value = make_contacts()

    email_patterns = MagicMock()
    email_patterns.discover.return_value = make_email_patterns()

    intelligence = MagicMock()
    intelligence.build.return_value = make_intelligence()

    defaults: dict[str, Any] = {
        "crawler_service": crawler,
        "company_profile_service": company_profile,
        "technology_service": technology,
        "mobile_service": mobile,
        "qualification_service": qualification,
        "contact_service": contacts,
        "email_pattern_service": email_patterns,
        "intelligence_service": intelligence,
    }
    defaults.update(overrides)
    return LeadProcessor(**defaults)


@pytest.mark.asyncio
async def test_successful_processing() -> None:
    processor = build_processor()
    lead = await processor.process(make_startup())

    assert lead.processing.success is True
    assert lead.website_profile is not None
    assert lead.company_profile is not None
    assert lead.technology_report is not None
    assert lead.mobile_report is not None
    assert lead.qualification_report is not None
    assert lead.contacts is not None
    assert lead.email_pattern_report is not None
    assert lead.lead_intelligence is not None
    assert lead.processing.errors == []
    assert len(lead.processing.stage_timings) >= 8


@pytest.mark.asyncio
async def test_crawler_failure_continues() -> None:
    crawler = AsyncMock()
    crawler.analyze = AsyncMock(side_effect=RuntimeError("network down"))
    processor = build_processor(crawler_service=crawler)

    lead = await processor.process(make_startup())

    assert lead.website_profile is None
    assert lead.company_profile is None
    assert lead.technology_report is None
    assert lead.contacts is None
    assert lead.qualification_report is not None
    assert any("crawler failed" in error for error in lead.processing.errors)
    assert lead.processing.success is False
    assert any(
        "Skipped enrichment stages dependent on WebsiteProfile" in warning
        for warning in lead.processing.warnings
    )


@pytest.mark.asyncio
async def test_technology_failure_partial_success() -> None:
    technology = MagicMock()
    technology.detect.side_effect = RuntimeError("tech boom")
    processor = build_processor(technology_service=technology)

    lead = await processor.process(make_startup())

    assert lead.website_profile is not None
    assert lead.technology_report is None
    assert lead.company_profile is not None
    assert lead.contacts is not None
    assert lead.lead_intelligence is not None
    assert any("technology failed" in error for error in lead.processing.errors)
    assert lead.processing.success is False


@pytest.mark.asyncio
async def test_contact_failure_continues() -> None:
    contacts = MagicMock()
    contacts.discover.side_effect = RuntimeError("no contacts")
    processor = build_processor(contact_service=contacts)

    lead = await processor.process(make_startup())

    assert lead.contacts is None
    assert lead.qualification_report is not None
    assert lead.lead_intelligence is not None
    assert any("contacts failed" in error for error in lead.processing.errors)
    assert lead.processing.success is False


@pytest.mark.asyncio
async def test_partial_success_report() -> None:
    technology = MagicMock()
    technology.detect.side_effect = RuntimeError("tech boom")
    contacts = MagicMock()
    contacts.discover.side_effect = RuntimeError("no contacts")
    processor = build_processor(
        technology_service=technology,
        contact_service=contacts,
    )

    lead = await processor.process(make_startup())
    report = lead.to_processing_report()

    assert report.success is False
    assert len(report.errors) >= 2
    assert "technology" in report.stage_durations
    assert "contacts" in report.stage_durations
    assert lead.company_profile is not None
    assert lead.mobile_report is not None


@pytest.mark.asyncio
async def test_stage_timing_recorded() -> None:
    processor = build_processor()
    lead = await processor.process(make_startup())

    stages = {timing.stage for timing in lead.processing.stage_timings}
    expected = {
        "crawler",
        "company_profile",
        "technology",
        "mobile",
        "contacts",
        "qualification",
        "lead_intelligence",
        "email_patterns",
    }
    assert expected.issubset(stages)
    assert lead.processing.total_duration_ms >= 0
    assert all(timing.duration_ms >= 0 for timing in lead.processing.stage_timings)


@pytest.mark.asyncio
async def test_pipeline_service_process_with_report() -> None:
    processor = build_processor()
    service = LeadPipelineService(processor=processor)

    lead, report = await service.process_with_report(make_startup())

    assert lead.processing.success is True
    assert report.success is True
    assert report.total_duration_ms == lead.processing.total_duration_ms
    assert set(report.stage_durations) == {timing.stage for timing in lead.processing.stage_timings}
