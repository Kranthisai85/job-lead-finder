from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.ai.client import OllamaClient
from app.ai.generator import AIEmailGenerator
from app.ai.prompts import (
    build_email_prompt,
    build_followup_prompt,
    build_prompt_context,
    parse_email_json,
)
from app.ai.service import AIEmailService
from app.ai.types import OllamaGenerateResponse
from app.company_profile.types import CompanyProfile
from app.contact_discovery.types import ContactCandidate, ContactDiscoveryReport
from app.crawler.types import WebsiteProfile
from app.intelligence.types import LeadIntelligence, LeadIntelligenceMetadata
from app.mobile_detection.types import MobileAppDetectionResult
from app.personalization.service import CompanyPersonalizationService
from app.personalization.types import PersonalizedEmailContext
from app.pipeline.types import CompleteLead, ProcessingMetadata, StartupSeed
from app.qualification.types import QualificationResult
from app.schemas.company import CompanyResponse
from app.technology.types import Technology, TechnologyReport


def make_lead() -> CompleteLead:
    return CompleteLead(
        startup=StartupSeed(
            name="Acme",
            website="https://acme.example",
            description="Issue tracking for software teams",
            source="test",
        ),
        website_profile=WebsiteProfile(
            url="https://acme.example",
            final_url="https://acme.example/",
            title="Acme",
            description="Issue tracking for software teams",
            valid=True,
            status_code=200,
        ),
        company_profile=CompanyProfile(
            company_name="Acme",
            short_description="Issue tracking for software teams",
            business_category="Developer Tools",
            industry="Project Management",
            product_type="SaaS",
            target_audience="Developers",
            confidence=0.8,
        ),
        technology_report=TechnologyReport(
            url="https://acme.example/",
            technologies=[
                Technology(name="React", category="frontend", confidence=90),
                Technology(name="Tailwind", category="frontend", confidence=80),
            ],
            detected_count=2,
        ),
        mobile_report=MobileAppDetectionResult(has_mobile_app=False, confidence=0.1),
        qualification_report=QualificationResult(
            qualified=True,
            score=80,
            reasons=["website present"],
        ),
        contacts=ContactDiscoveryReport(
            url="https://acme.example/",
            contacts=[
                ContactCandidate(
                    full_name="Ada Lovelace",
                    email="ada@acme.example",
                    role="founder",
                    confidence=0.9,
                )
            ],
            emails=["ada@acme.example"],
            contact_count=1,
        ),
        lead_intelligence=LeadIntelligence(
            company=CompanyResponse(
                id="1",
                name="Acme",
                website="acme.example",
                description="Issue tracking",
                industry="Project Management",
                source="test",
                created_at=datetime.now(timezone.utc),
            ),
            metadata=LeadIntelligenceMetadata(collector_name="test"),
        ),
        processing=ProcessingMetadata(success=True),
    )


def make_personalized() -> PersonalizedEmailContext:
    lead = make_lead()
    return CompanyPersonalizationService().generate(lead)


def ollama_json_response(payload: dict[str, str]) -> OllamaGenerateResponse:
    return OllamaGenerateResponse(
        model="qwen2.5:7b",
        response=json.dumps(payload),
        done=True,
        eval_count=42,
    )


def test_prompt_building_includes_required_fields() -> None:
    lead = make_lead()
    personalized = make_personalized()
    context = build_prompt_context(lead, personalized)
    prompt = build_email_prompt(context)

    assert "Acme" in prompt
    assert "Developer Tools" in prompt
    assert "Project Management" in prompt
    assert "React" in prompt
    assert "Ada Lovelace" in prompt
    assert "Lead score:" in prompt
    assert "subject" in prompt


def test_followup_prompt_includes_previous_subject() -> None:
    lead = make_lead()
    personalized = make_personalized()
    context = build_prompt_context(lead, personalized)
    prompt = build_followup_prompt(context, previous_subject="Hello Acme", days_since_sent=5)
    assert "Hello Acme" in prompt
    assert "5 days" in prompt


def test_parse_email_json_from_markdown_block() -> None:
    raw = """```json
{"subject": "Hi", "opening": "Hello", "body": "Body", "cta": "Call?"}
```"""
    parsed = parse_email_json(raw)
    assert parsed["subject"] == "Hi"
    assert parsed["opening"] == "Hello"


@pytest.mark.asyncio
async def test_successful_generation() -> None:
    client = AsyncMock()
    client.generate = AsyncMock(
        return_value=ollama_json_response(
            {
                "subject": "Flutter for Acme",
                "opening": "Hi Ada,",
                "body": "I noticed Acme uses React.",
                "cta": "Open to a quick call?",
                "signature": "{{sender_name}}",
            }
        )
    )
    client.model = "qwen2.5:7b"

    generator = AIEmailGenerator(client=client)
    email = await generator.generate_email(make_lead())

    assert email.generation_source == "ollama"
    assert email.subject == "Flutter for Acme"
    assert email.opening == "Hi Ada,"
    assert email.token_estimate > 0
    client.generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_fallback_when_ollama_unavailable() -> None:
    client = AsyncMock()
    client.generate = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    client.model = "qwen2.5:7b"

    generator = AIEmailGenerator(client=client)
    email = await generator.generate_email(make_lead())

    assert email.generation_source == "fallback"
    assert email.subject
    assert email.opening
    assert email.body
    assert email.cta
    assert email.errors
    assert any("fallback" in warning.lower() for warning in email.warnings)


@pytest.mark.asyncio
async def test_service_generate_never_raises() -> None:
    client = AsyncMock()
    client.generate = AsyncMock(side_effect=RuntimeError("boom"))
    client.model = "qwen2.5:7b"

    service = AIEmailService(generator=AIEmailGenerator(client=client))
    email = await service.generate(make_lead())
    assert email.generation_source == "fallback"


@pytest.mark.asyncio
async def test_retry_on_transient_failure() -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "model": "qwen2.5:7b",
        "response": json.dumps(
            {
                "subject": "Retry ok",
                "opening": "Hi",
                "body": "Body",
                "cta": "CTA",
            }
        ),
        "done": True,
    }

    http_client = AsyncMock()
    http_client.post = AsyncMock(
        side_effect=[
            httpx.ConnectError("down"),
            httpx.ConnectError("down again"),
            mock_response,
        ]
    )

    client = OllamaClient(client=http_client, max_retries=2)
    result = await client.generate("test prompt")
    assert "Retry ok" in result.response
    assert http_client.post.await_count == 3


@pytest.mark.asyncio
async def test_timeout_triggers_fallback() -> None:
    client = AsyncMock()
    client.generate = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
    client.model = "qwen2.5:7b"

    email = await AIEmailGenerator(client=client).generate_email(make_lead())
    assert email.generation_source == "fallback"
    assert email.errors


@pytest.mark.asyncio
async def test_generate_followup() -> None:
    client = AsyncMock()
    client.generate = AsyncMock(
        return_value=ollama_json_response(
            {
                "subject": "Following up on Acme",
                "opening": "Hi again,",
                "body": "Just checking in.",
                "cta": "Still open to chat?",
            }
        )
    )
    client.model = "qwen2.5:7b"

    email = await AIEmailGenerator(client=client).generate_followup(
        make_lead(),
        previous_subject="Original subject",
        days_since_sent=4,
    )
    assert email.subject == "Following up on Acme"
    assert email.generation_source == "ollama"


@pytest.mark.asyncio
async def test_generate_subject() -> None:
    client = AsyncMock()
    client.generate = AsyncMock(
        return_value=ollama_json_response({"subject": "Mobile idea for Acme"})
    )
    client.model = "qwen2.5:7b"

    email = await AIEmailGenerator(client=client).generate_subject(make_lead())
    assert email.subject == "Mobile idea for Acme"


@pytest.mark.asyncio
async def test_invalid_json_response_uses_fallback() -> None:
    client = AsyncMock()
    client.generate = AsyncMock(
        return_value=OllamaGenerateResponse(model="qwen2.5:7b", response="not json", done=True)
    )
    client.model = "qwen2.5:7b"

    email = await AIEmailGenerator(client=client).generate_email(make_lead())
    assert email.generation_source == "fallback"
