from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.company_profile.types import CompanyProfile
from app.contact_discovery.types import ContactCandidate, ContactDiscoveryReport
from app.crawler.types import WebsiteProfile
from app.email_patterns.types import EmailPattern, EmailPatternReport
from app.exceptions import RepositoryError
from app.intelligence.types import LeadIntelligence, LeadIntelligenceMetadata
from app.lead_scoring.service import LeadScoringService
from app.mobile_detection.types import MobileAppDetectionResult
from app.pipeline.persistence import EMAIL_PATTERN_TAG_PREFIX, PipelinePersistenceService
from app.pipeline.service import LeadPipelineService
from app.pipeline.types import CompleteLead, ProcessingMetadata, StartupSeed
from app.qualification.types import QualificationResult
from app.repositories.company_repository import CompanyRepository
from app.repositories.contact_repository import ContactRepository
from app.schemas.company import CompanyResponse
from app.technology.types import Technology, TechnologyReport
from app.validation.validation_runner import ValidationPipeline


def make_lead(
    *,
    name: str = "Acme",
    website: str = "https://acme.example",
    emails: list[str] | None = None,
    contacts: list[ContactCandidate] | None = None,
    inferred_pattern: str | None = "{first}",
) -> CompleteLead:
    contact_list = contacts or [
        ContactCandidate(
            full_name="Ada Lovelace",
            first_name="Ada",
            last_name="Lovelace",
            email=(emails[0] if emails else "ada@acme.example"),
            role="founder",
            confidence=0.9,
        )
    ]
    email_list = emails or ["ada@acme.example"]
    return CompleteLead(
        startup=StartupSeed(
            name=name,
            website=website,
            description="Issue tracking for teams",
            source="test",
        ),
        website_profile=WebsiteProfile(
            url=website,
            final_url=website,
            title=name,
            description="Issue tracking for teams",
            valid=True,
            status_code=200,
        ),
        company_profile=CompanyProfile(
            company_name=name,
            short_description="Issue tracking for teams",
            business_category="Developer Tools",
            industry="Project Management",
            product_type="SaaS",
            headquarters="San Francisco, CA",
            confidence=0.8,
        ),
        technology_report=TechnologyReport(
            url=website,
            technologies=[Technology(name="React", category="frontend", confidence=90)],
            detected_count=1,
        ),
        mobile_report=MobileAppDetectionResult(has_mobile_app=False, confidence=0.1),
        qualification_report=QualificationResult(
            qualified=True, score=80, reasons=["website present"]
        ),
        contacts=ContactDiscoveryReport(
            url=website,
            contacts=contact_list,
            emails=email_list,
            contact_count=len(contact_list),
        ),
        email_pattern_report=(
            EmailPatternReport(
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
                inferred_pattern=inferred_pattern,
                confidence=0.8,
            )
            if inferred_pattern
            else None
        ),
        lead_intelligence=LeadIntelligence(
            company=CompanyResponse(
                id="temp",
                name=name,
                website="acme.example",
                description="Issue tracking for teams",
                industry="Project Management",
                source="test",
                created_at=datetime.now(timezone.utc),
            ),
            metadata=LeadIntelligenceMetadata(collector_name="test"),
        ),
        processing=ProcessingMetadata(success=True),
    )


@pytest.mark.asyncio
async def test_persist_new_company(test_db: Any) -> None:
    service = PipelinePersistenceService()
    lead = make_lead()
    lead.outbound_lead_score = LeadScoringService().score(lead)
    result = await service.persist(lead)

    assert result.company_created is True
    assert result.company_updated is False
    assert result.company_id is not None
    assert result.contacts_created == 1
    assert result.email_pattern_saved is True

    company = await CompanyRepository().find_by_id(result.company_id)
    assert company is not None
    assert company.website == "acme.example"
    assert company.has_mobile_app is False
    assert company.is_flutter_lead is False
    assert company.qualification_score == lead.outbound_lead_score.score
    assert company.qualification_status == lead.outbound_lead_score.status.value
    assert company.qualification_reasons == list(lead.outbound_lead_score.reasons)
    assert any(tag.startswith(EMAIL_PATTERN_TAG_PREFIX) for tag in company.tags)
    assert await ContactRepository().count({"company_id": result.company_id}) == 1


@pytest.mark.asyncio
async def test_persist_is_flutter_lead_false_without_flutter_evidence(test_db: Any) -> None:
    """Qualified + contacts + no mobile app alone must not set is_flutter_lead."""
    lead = make_lead(name="NoFlutterCo", website="https://noflutter.example")
    assert lead.qualification_report is not None and lead.qualification_report.qualified is True
    assert lead.mobile_report is not None and lead.mobile_report.has_mobile_app is False
    assert lead.contacts is not None and lead.contacts.contact_count > 0
    assert all(
        tech.name.lower() not in {"flutter", "dart"} for tech in lead.technology_report.technologies
    )

    result = await PipelinePersistenceService().persist(lead)
    company = await CompanyRepository().find_by_id(result.company_id)
    assert company is not None
    assert company.is_flutter_lead is False


@pytest.mark.asyncio
async def test_persist_is_flutter_lead_true_with_flutter_technology(test_db: Any) -> None:
    lead = make_lead(name="FlutterCo", website="https://flutterco.example")
    lead.technology_report = TechnologyReport(
        url=lead.startup.website,
        technologies=[
            Technology(name="Flutter", category="mobile", confidence=95),
            Technology(name="Firebase", category="backend", confidence=80),
        ],
        detected_count=2,
    )

    result = await PipelinePersistenceService().persist(lead)
    company = await CompanyRepository().find_by_id(result.company_id)
    assert company is not None
    assert company.is_flutter_lead is True
    assert company.has_mobile_app is False


@pytest.mark.asyncio
async def test_persist_duplicate_company_updates(test_db: Any) -> None:
    service = PipelinePersistenceService()
    first = await service.persist(make_lead())
    second = await service.persist(
        make_lead(
            name="Acme Updated",
            contacts=[
                ContactCandidate(
                    full_name="Ada Lovelace",
                    email="ada@acme.example",
                    role="ceo",
                    confidence=0.95,
                )
            ],
        )
    )

    assert first.company_created is True
    assert second.company_created is False
    assert second.company_updated is True
    assert second.company_id == first.company_id
    assert second.contacts_updated == 1
    assert second.contacts_created == 0

    company = await CompanyRepository().find_by_id(first.company_id)  # type: ignore[arg-type]
    assert company is not None
    assert company.name == "Acme Updated"
    contact = await ContactRepository().find_one({"email": "ada@acme.example"})
    assert contact is not None
    assert contact.role == "ceo"
    assert await CompanyRepository().count() == 1


@pytest.mark.asyncio
async def test_persist_contact_update_by_email(test_db: Any) -> None:
    service = PipelinePersistenceService()
    await service.persist(make_lead())
    result = await service.persist(
        make_lead(
            contacts=[
                ContactCandidate(
                    full_name="Ada L.",
                    email="ada@acme.example",
                    linkedin="https://linkedin.com/in/ada",
                    confidence=0.99,
                )
            ]
        )
    )

    assert result.contacts_updated == 1
    contact = await ContactRepository().find_one({"email": "ada@acme.example"})
    assert contact is not None
    assert contact.full_name == "Ada L."
    assert contact.linkedin_url == "https://linkedin.com/in/ada"
    assert await ContactRepository().count() == 1


@pytest.mark.asyncio
async def test_persist_disabled_validation_pipeline(test_db: Any) -> None:
    pipeline = ValidationPipeline(persistence_service=None)
    assert pipeline.persistence_service is None
    assert await CompanyRepository().count() == 0


@pytest.mark.asyncio
async def test_process_and_persist_enabled(test_db: Any) -> None:
    processor = MagicMock()
    processor.process = AsyncMock(return_value=make_lead())
    service = LeadPipelineService(
        processor=processor,
        persistence_service=PipelinePersistenceService(),
    )

    lead, persist_result = await service.process_and_persist(
        StartupSeed(name="Acme", website="https://acme.example", source="test")
    )

    assert lead.startup.name == "Acme"
    assert persist_result.company_created is True
    assert await CompanyRepository().count() == 1


@pytest.mark.asyncio
async def test_process_without_persist_does_not_write(test_db: Any) -> None:
    processor = MagicMock()
    processor.process = AsyncMock(return_value=make_lead())
    service = LeadPipelineService(processor=processor)

    await service.process(StartupSeed(name="Acme", website="https://acme.example", source="test"))

    assert await CompanyRepository().count() == 0


@pytest.mark.asyncio
async def test_persist_repository_failure(test_db: Any) -> None:
    company_repository = MagicMock()
    company_repository.find_one = AsyncMock(side_effect=RepositoryError("boom"))
    service = PipelinePersistenceService(company_repository=company_repository)

    result = await service.persist(make_lead())

    assert result.company_id is None
    assert result.errors
    assert "company persistence failed (repository)" in result.errors[0]
    assert "boom" in result.errors[0]


@pytest.mark.asyncio
async def test_persist_validation_error_includes_message(test_db: Any) -> None:
    from pydantic import ValidationError

    company_service = MagicMock()
    company_service.create_company = AsyncMock(
        side_effect=ValidationError.from_exception_data(
            "CreateCompanyRequest",
            [
                {
                    "type": "string_too_short",
                    "loc": ("name",),
                    "input": "",
                    "ctx": {"min_length": 1},
                }
            ],
        )
    )
    company_repository = MagicMock()
    company_repository.find_one = AsyncMock(return_value=None)
    service = PipelinePersistenceService(
        company_service=company_service,
        company_repository=company_repository,
    )

    result = await service.persist(make_lead())

    assert result.company_id is None
    assert result.errors
    assert "company persistence failed (validation)" in result.errors[0]
    assert "ValidationError" in result.errors[0]


@pytest.mark.asyncio
async def test_persist_duplicate_key_error_includes_message(test_db: Any) -> None:
    from pymongo.errors import DuplicateKeyError

    company_repository = MagicMock()
    company_repository.find_one = AsyncMock(side_effect=DuplicateKeyError("E11000 duplicate"))
    service = PipelinePersistenceService(company_repository=company_repository)

    result = await service.persist(make_lead())

    assert result.company_id is None
    assert result.errors
    assert "company persistence failed (duplicate_key)" in result.errors[0]
    assert "E11000" in result.errors[0]


@pytest.mark.asyncio
async def test_persist_empty_exception_message_uses_type_name(test_db: Any) -> None:
    company_repository = MagicMock()
    company_repository.find_one = AsyncMock(side_effect=RuntimeError())
    service = PipelinePersistenceService(company_repository=company_repository)

    result = await service.persist(make_lead())

    assert result.company_id is None
    assert result.errors
    assert "company persistence failed (service)" in result.errors[0]
    assert "RuntimeError" in result.errors[0]


@pytest.mark.asyncio
async def test_persist_skips_invalid_website(test_db: Any) -> None:
    lead = make_lead(website="   ")
    result = await PipelinePersistenceService().persist(lead)
    assert result.skipped is True
    assert result.company_id is None
    assert await CompanyRepository().count() == 0
