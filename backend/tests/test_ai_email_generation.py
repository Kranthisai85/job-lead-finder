from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.ai.client import OllamaClient, OllamaModelNotFoundError, format_ollama_error
from app.ai.generator import AIEmailGenerator
from app.ai.prompts import (
    build_email_prompt,
    build_fallback_subject,
    build_followup_prompt,
    build_prompt_context,
    is_generic_subject,
    parse_email_json,
    should_replace_subject,
    subject_uses_wrong_example_brand,
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
    assert "https://acme.example" in prompt
    assert "Developer Tools" in prompt
    assert "Project Management" in prompt
    assert "React" in prompt
    assert "Ada" in prompt
    assert "(founder)" in prompt
    assert "ada@acme.example" in prompt
    assert "Lead score:" in prompt
    assert "Flutter/Dart evidence: no" in prompt
    assert "Do not invent" in prompt
    assert "ChatGPT" in prompt
    assert "quick thought on" in prompt  # banned pattern called out in guide
    assert "tech stack" in prompt.lower() or "Stack signals" in prompt
    assert "What they build" in prompt
    assert "Company brand name:" in prompt
    assert "subject" in prompt


def test_fallback_subject_is_varied_and_not_generic() -> None:
    assert is_generic_subject("quick thought on Univex Browser") is True
    assert is_generic_subject("Univex outside the browser?") is False
    assert subject_uses_wrong_example_brand("Univex outside the browser?", "Frekil") is True
    assert subject_uses_wrong_example_brand("Frekil outside the browser?", "Frekil") is False
    assert should_replace_subject("Univex outside the browser?", "Frekil") is True

    subjects = {
        build_fallback_subject(
            company_name=name,
            product_description=desc,
            has_mobile_app=False,
        )
        for name, desc in (
            ("Univex Browser", "privacy-focused browser for teams"),
            ("Dojo", "coding practice platform for developers"),
            ("Pesterly", "reminders that don't feel like nagging"),
            ("Zephyrax", "monster battle arena game"),
        )
    }
    assert len(subjects) >= 3
    for subject in subjects:
        assert "quick thought on" not in subject.lower()
        assert is_generic_subject(subject) is False


def test_prompt_includes_flutter_evidence_when_present() -> None:
    lead = make_lead()
    lead.technology_report = TechnologyReport(
        url="https://acme.example/",
        technologies=[Technology(name="Flutter", category="mobile", confidence=95)],
        detected_count=1,
    )
    personalized = CompanyPersonalizationService().generate(lead)
    assert personalized.is_flutter_lead is True
    context = build_prompt_context(lead, personalized)
    prompt = build_email_prompt(context)

    assert "Flutter/Dart evidence: yes" in prompt
    assert "Flutter" in prompt
    assert "never mention" in prompt.lower() or "INTERNAL ONLY" in prompt


def test_prompt_does_not_claim_flutter_without_evidence() -> None:
    lead = make_lead()
    personalized = CompanyPersonalizationService().generate(lead)
    assert personalized.is_flutter_lead is False
    context = build_prompt_context(lead, personalized)
    prompt = build_email_prompt(context)

    assert "Flutter/Dart evidence: no" in prompt
    assert "Flutter-based mobile product" not in prompt


def test_prompt_isolated_per_company_and_contact() -> None:
    lead_a = make_lead()
    lead_b = CompleteLead(
        startup=StartupSeed(
            name="BetaSoft",
            website="https://beta.example",
            description="Payroll automation for remote teams",
            source="test",
        ),
        company_profile=CompanyProfile(
            company_name="BetaSoft",
            short_description="Payroll automation for remote teams",
            business_category="HR",
            industry="Payroll",
            product_type="SaaS",
            target_audience="HR Teams",
            confidence=0.8,
        ),
        technology_report=TechnologyReport(
            url="https://beta.example/",
            technologies=[Technology(name="Vue", category="frontend", confidence=90)],
            detected_count=1,
        ),
        mobile_report=MobileAppDetectionResult(has_mobile_app=False, confidence=0.1),
        contacts=ContactDiscoveryReport(
            url="https://beta.example/",
            contacts=[
                ContactCandidate(
                    full_name="Grace Hopper",
                    email="grace@beta.example",
                    role="CEO",
                    confidence=0.9,
                )
            ],
            emails=["grace@beta.example"],
            contact_count=1,
        ),
        processing=ProcessingMetadata(success=True),
    )

    prompt_a = build_email_prompt(
        build_prompt_context(lead_a, CompanyPersonalizationService().generate(lead_a))
    )
    prompt_b = build_email_prompt(
        build_prompt_context(lead_b, CompanyPersonalizationService().generate(lead_b))
    )

    assert "Acme" in prompt_a
    assert "Ada" in prompt_a
    assert "https://acme.example" in prompt_a
    assert "BetaSoft" not in prompt_a
    assert "Grace Hopper" not in prompt_a
    assert "beta.example" not in prompt_a

    assert "BetaSoft" in prompt_b
    assert "Grace" in prompt_b
    assert "(CEO)" in prompt_b
    assert "https://beta.example" in prompt_b
    assert "Acme" not in prompt_b
    assert "Ada" not in prompt_b
    assert "acme.example" not in prompt_b


@pytest.mark.asyncio
async def test_sparse_lead_does_not_crash_email_generation() -> None:
    sparse = CompleteLead(
        startup=StartupSeed(name="SparseCo", website="https://sparse.example", source="test"),
        processing=ProcessingMetadata(success=True),
    )
    client = AsyncMock()
    client.generate = AsyncMock(
        return_value=ollama_json_response(
            {
                "subject": "Idea for SparseCo",
                "opening": "Hi,",
                "body": "Quick note.",
                "cta": "Open to a call?",
            }
        )
    )
    client.model = "qwen2.5:7b"

    email = await AIEmailGenerator(client=client).generate_email(sparse)
    assert email.generation_source == "ollama"
    assert email.subject
    prompt = client.generate.await_args.args[0]
    assert "SparseCo" in prompt
    assert "https://sparse.example" in prompt
    assert "Flutter/Dart evidence: no" in prompt


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


def test_parse_email_json_rejects_missing_required_fields() -> None:
    with pytest.raises(ValueError, match="Missing required fields"):
        parse_email_json('{"subject": "Hi", "opening": "Hello"}')


def test_parse_email_json_rejects_markdown_in_values() -> None:
    raw = json.dumps(
        {
            "subject": "Hi",
            "opening": "Hello",
            "body": "```code```",
            "cta": "Call?",
        }
    )
    with pytest.raises(ValueError, match="markdown code fences"):
        parse_email_json(raw)


def test_parse_email_json_subject_only() -> None:
    parsed = parse_email_json('{"subject": "Mobile idea"}', required_fields=("subject",))
    assert parsed["subject"] == "Mobile idea"


@pytest.mark.asyncio
async def test_successful_generation() -> None:
    client = AsyncMock()
    client.generate = AsyncMock(
        return_value=ollama_json_response(
            {
                "subject": "Acme on mobile?",
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
    assert email.subject == "Acme on mobile?"
    assert email.opening == "Hi Ada,"
    assert email.token_estimate > 0
    assert "```" not in email.subject
    assert "```" not in email.body
    client.generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_e2e_lead_personalization_ai_email_for_one_company() -> None:
    """CompleteLead → personalization → prompt → mocked Ollama → validated email."""
    lead = CompleteLead(
        startup=StartupSeed(
            name="FlutterPulse",
            website="https://flutterpulse.example",
            description="Analytics dashboards for product teams shipping Flutter apps.",
            source="producthunt",
        ),
        website_profile=WebsiteProfile(
            url="https://flutterpulse.example",
            final_url="https://flutterpulse.example/",
            title="FlutterPulse",
            description="Analytics dashboards for product teams shipping Flutter apps.",
            valid=True,
            status_code=200,
        ),
        company_profile=CompanyProfile(
            company_name="FlutterPulse",
            short_description="Analytics dashboards for product teams shipping Flutter apps.",
            business_category="Analytics",
            industry="Product Analytics",
            product_type="SaaS",
            target_audience="Startups",
            confidence=0.9,
        ),
        technology_report=TechnologyReport(
            url="https://flutterpulse.example/",
            technologies=[
                Technology(name="Flutter", category="mobile", confidence=95),
                Technology(name="Dart", category="language", confidence=90),
                Technology(name="Firebase", category="backend", confidence=80),
            ],
            detected_count=3,
        ),
        mobile_report=MobileAppDetectionResult(has_mobile_app=False, confidence=0.1),
        qualification_report=QualificationResult(
            qualified=True,
            score=85,
            reasons=["website present", "Flutter mentioned"],
        ),
        contacts=ContactDiscoveryReport(
            url="https://flutterpulse.example/",
            contacts=[
                ContactCandidate(
                    full_name="Maya Chen",
                    email="maya@flutterpulse.example",
                    role="Founder",
                    confidence=0.95,
                )
            ],
            emails=["maya@flutterpulse.example"],
            contact_count=1,
        ),
        processing=ProcessingMetadata(success=True),
    )

    client = AsyncMock()
    client.generate = AsyncMock(
        return_value=ollama_json_response(
            {
                "subject": "Flutter mobile idea for FlutterPulse",
                "opening": "Hi Maya,",
                "body": (
                    "I noticed FlutterPulse builds analytics for Flutter teams "
                    "and does not yet ship a native mobile app."
                ),
                "cta": "Would you be open to a short conversation?",
                "signature": "{{sender_name}}",
            }
        )
    )
    client.model = "qwen2.5:7b"

    # Same public entrypoint used by LeadGenerationOrchestrator.
    service = AIEmailService(generator=AIEmailGenerator(client=client))
    email = await service.generate(lead)

    assert client.generate.await_count == 1
    prompt = client.generate.await_args.args[0]

    assert "Company brand name: FlutterPulse" in prompt
    assert "Website: https://flutterpulse.example" in prompt
    assert "Analytics dashboards for product teams shipping Flutter apps." in prompt
    assert "Maya" in prompt
    assert "(Founder)" in prompt
    assert "maya@flutterpulse.example" in prompt
    assert "Flutter" in prompt
    assert "Dart" in prompt
    assert "Firebase" in prompt
    assert "Flutter/Dart evidence: yes" in prompt
    assert "couldn't find a mobile app" in prompt or "Native mobile app found: no" in prompt
    assert "Acme" not in prompt
    assert "BetaSoft" not in prompt
    assert "ada@acme.example" not in prompt

    assert email.generation_source == "ollama"
    assert email.errors == []
    assert email.subject == "Flutter mobile idea for FlutterPulse"
    assert email.opening == "Hi Maya,"
    assert email.body
    assert email.cta
    assert email.signature == "{{sender_name}}"
    assert "```" not in email.subject
    assert "```" not in email.opening
    assert "```" not in email.body
    assert "```" not in email.cta
    assert "BetaSoft" not in email.subject
    assert "Acme" not in email.body


@pytest.mark.asyncio
async def test_e2e_ai_email_prompts_isolated_between_companies() -> None:
    """Two sequential generations must never mix company/contact/tech into each other's prompts."""
    lead_a = make_lead()  # Acme / Ada / React
    lead_b = CompleteLead(
        startup=StartupSeed(
            name="NovaLedger",
            website="https://novaledger.example",
            description="Bookkeeping automation for SMBs.",
            source="test",
        ),
        company_profile=CompanyProfile(
            company_name="NovaLedger",
            short_description="Bookkeeping automation for SMBs.",
            business_category="Fintech",
            industry="Accounting",
            product_type="SaaS",
            target_audience="SMBs",
            confidence=0.8,
        ),
        technology_report=TechnologyReport(
            url="https://novaledger.example/",
            technologies=[Technology(name="Next.js", category="framework", confidence=90)],
            detected_count=1,
        ),
        mobile_report=MobileAppDetectionResult(has_mobile_app=False, confidence=0.1),
        contacts=ContactDiscoveryReport(
            url="https://novaledger.example/",
            contacts=[
                ContactCandidate(
                    full_name="Sam Ortiz",
                    email="sam@novaledger.example",
                    role="CEO",
                    confidence=0.9,
                )
            ],
            emails=["sam@novaledger.example"],
            contact_count=1,
        ),
        processing=ProcessingMetadata(success=True),
    )

    prompts: list[str] = []

    async def capture_generate(prompt: str) -> OllamaGenerateResponse:
        prompts.append(prompt)
        company = "NovaLedger" if "NovaLedger" in prompt else "Acme"
        return ollama_json_response(
            {
                "subject": f"Idea for {company}",
                "opening": "Hello,",
                "body": f"Note about {company}.",
                "cta": "Open to a call?",
            }
        )

    client = AsyncMock()
    client.generate = AsyncMock(side_effect=capture_generate)
    client.model = "qwen2.5:7b"
    service = AIEmailService(generator=AIEmailGenerator(client=client))

    email_a = await service.generate(lead_a)
    email_b = await service.generate(lead_b)

    assert len(prompts) == 2
    prompt_a, prompt_b = prompts

    assert "Company brand name: Acme" in prompt_a
    assert "https://acme.example" in prompt_a
    assert "Ada" in prompt_a
    assert "React" in prompt_a
    assert "NovaLedger" not in prompt_a
    assert "Sam Ortiz" not in prompt_a
    assert "novaledger.example" not in prompt_a
    assert "Next.js" not in prompt_a

    assert "Company brand name: NovaLedger" in prompt_b
    assert "https://novaledger.example" in prompt_b
    assert "Sam" in prompt_b
    assert "(CEO)" in prompt_b
    assert "Next.js" in prompt_b
    assert "Flutter/Dart evidence: no" in prompt_b
    assert "Acme" not in prompt_b
    assert "Ada" not in prompt_b
    assert "acme.example" not in prompt_b

    assert email_a.generation_source == "ollama"
    assert email_b.generation_source == "ollama"
    assert "Acme" in email_a.subject
    assert "NovaLedger" in email_b.subject
    assert "NovaLedger" not in email_a.subject
    assert "Acme" not in email_b.subject


@pytest.mark.asyncio
async def test_malformed_json_uses_fallback() -> None:
    client = AsyncMock()
    client.generate = AsyncMock(
        return_value=OllamaGenerateResponse(
            model="qwen2.5:7b",
            response='{"subject": "Hi", "opening": "unterminated',
            done=True,
        )
    )
    client.model = "qwen2.5:7b"

    email = await AIEmailGenerator(client=client).generate_email(make_lead())
    assert email.generation_source == "fallback"
    assert email.errors


@pytest.mark.asyncio
async def test_missing_required_field_uses_fallback() -> None:
    client = AsyncMock()
    client.generate = AsyncMock(
        return_value=ollama_json_response(
            {
                "subject": "Only subject",
                "opening": "",
                "body": "",
                "cta": "",
            }
        )
    )
    client.model = "qwen2.5:7b"

    email = await AIEmailGenerator(client=client).generate_email(make_lead())
    assert email.generation_source == "fallback"
    assert any("Missing required fields" in error for error in email.errors)


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


def test_format_ollama_error_handles_empty_exception_message() -> None:
    exc = httpx.ConnectError("")
    exc.__cause__ = ConnectionRefusedError(111, "Connection refused")

    detail = format_ollama_error(
        exc,
        url="http://172.17.0.1:11434/api/generate",
        timeout=60.0,
    )

    assert "type=ConnectError" in detail
    assert "url=http://172.17.0.1:11434/api/generate" in detail
    assert "timeout=60.0" in detail
    assert "cause=ConnectionRefusedError" in detail
    assert "Connection refused" in detail


@pytest.mark.asyncio
async def test_retry_on_transient_failure(caplog: pytest.LogCaptureFixture) -> None:
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

    # Empty-message ConnectError mimics real httpx behavior on the VPS.
    empty_connect = httpx.ConnectError("")
    empty_connect.__cause__ = OSError(111, "Connection refused")

    http_client = AsyncMock()
    http_client.post = AsyncMock(
        side_effect=[
            empty_connect,
            httpx.ConnectError("down again"),
            mock_response,
        ]
    )

    client = OllamaClient(
        client=http_client,
        max_retries=2,
        base_url="http://172.17.0.1:11434",
        timeout=60.0,
    )
    client._model_verified = True
    with caplog.at_level("WARNING"):
        result = await client.generate("test prompt")

    assert "Retry ok" in result.response
    assert http_client.post.await_count == 3

    transient_logs = [
        record.getMessage()
        for record in caplog.records
        if "ollama_transient_failure" in record.getMessage()
    ]
    assert len(transient_logs) == 2
    for message in transient_logs:
        assert "type=ConnectError" in message
        assert "url=http://172.17.0.1:11434/api/generate" in message
        assert "timeout=60.0" in message
        assert "error=type=ConnectError" in message


@pytest.mark.asyncio
async def test_server_error_logs_status_and_body(caplog: pytest.LogCaptureFixture) -> None:
    request = httpx.Request("POST", "http://ollama.local/api/generate")
    response = httpx.Response(503, request=request, text="model loading")
    http_client = AsyncMock()
    http_client.post = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Server Error",
            request=request,
            response=response,
        )
    )

    client = OllamaClient(client=http_client, max_retries=0, timeout=12.0)
    client._model_verified = True
    with caplog.at_level("WARNING"), pytest.raises(httpx.HTTPStatusError):
        await client.generate("test prompt")

    server_logs = [
        record.getMessage()
        for record in caplog.records
        if "ollama_server_error" in record.getMessage()
    ]
    assert len(server_logs) == 1
    assert "type=HTTPStatusError" in server_logs[0]
    assert "status=503" in server_logs[0]
    assert "body=model loading" in server_logs[0]
    assert "url=http://ollama.local/api/generate" in server_logs[0]
    assert "timeout=12.0" in server_logs[0]


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
        return_value=ollama_json_response({"subject": "Acme outside the browser?"})
    )
    client.model = "qwen2.5:7b"

    email = await AIEmailGenerator(client=client).generate_subject(make_lead())
    assert email.subject == "Acme outside the browser?"


@pytest.mark.asyncio
async def test_generic_ollama_subject_is_replaced() -> None:
    client = AsyncMock()
    client.generate = AsyncMock(
        return_value=ollama_json_response(
            {
                "subject": "quick thought on Acme",
                "opening": "Hi Ada,",
                "body": "Body",
                "cta": "Call?",
            }
        )
    )
    client.model = "qwen2.5:7b"

    email = await AIEmailGenerator(client=client).generate_email(make_lead())
    assert email.generation_source == "ollama"
    assert "quick thought on" not in email.subject.lower()
    assert is_generic_subject(email.subject) is False


@pytest.mark.asyncio
async def test_copied_univex_example_subject_is_replaced() -> None:
    client = AsyncMock()
    client.generate = AsyncMock(
        return_value=ollama_json_response(
            {
                "subject": "Univex outside the browser?",
                "opening": "Hi Ada,",
                "body": "Body about Acme",
                "cta": "Open to a chat?",
            }
        )
    )
    client.model = "qwen2.5:7b"

    email = await AIEmailGenerator(client=client).generate_email(make_lead())
    assert email.generation_source == "ollama"
    assert "univex" not in email.subject.lower()
    assert "Acme" in email.subject or "acme" in email.subject.lower()


@pytest.mark.asyncio
async def test_invalid_json_response_uses_fallback() -> None:
    client = AsyncMock()
    client.generate = AsyncMock(
        return_value=OllamaGenerateResponse(model="qwen2.5:7b", response="not json", done=True)
    )
    client.model = "qwen2.5:7b"

    email = await AIEmailGenerator(client=client).generate_email(make_lead())
    assert email.generation_source == "fallback"


def _tags_response(models: list[str]) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"models": [{"name": name} for name in models]}
    return response


@pytest.mark.asyncio
async def test_missing_ollama_model_falls_back(caplog: pytest.LogCaptureFixture) -> None:
    generate_response = MagicMock()
    generate_response.raise_for_status = MagicMock()
    generate_response.json.return_value = {
        "model": "llama3.2:3b",
        "response": json.dumps(
            {"subject": "Hi", "opening": "Hello", "body": "Body", "cta": "Call?"}
        ),
        "done": True,
    }

    http_client = AsyncMock()
    http_client.get = AsyncMock(return_value=_tags_response(["llama3.2:3b"]))
    http_client.post = AsyncMock(return_value=generate_response)

    client = OllamaClient(
        client=http_client,
        model="qwen2.5:1.5b",
        max_retries=0,
        base_url="http://ollama.local",
    )
    with caplog.at_level("WARNING"):
        result = await client.generate("prompt")

    assert client.model == "llama3.2:3b"
    assert "Hi" in result.response
    assert http_client.post.await_count == 1
    assert any("ollama_model_missing" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_missing_ollama_model_with_no_installed_models_raises() -> None:
    http_client = AsyncMock()
    http_client.get = AsyncMock(return_value=_tags_response([]))
    http_client.post = AsyncMock()

    client = OllamaClient(client=http_client, model="qwen2.5:1.5b", max_retries=2)
    with pytest.raises(OllamaModelNotFoundError, match="no installed models"):
        await client.generate("prompt")

    http_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_http_404_model_not_found_does_not_retry(
    caplog: pytest.LogCaptureFixture,
) -> None:
    request = httpx.Request("POST", "http://ollama.local/api/generate")
    not_found = httpx.Response(
        404,
        request=request,
        text='{"error":"model \'qwen2.5:1.5b\' not found"}',
    )
    http_error = httpx.HTTPStatusError("Not Found", request=request, response=not_found)

    http_client = AsyncMock()
    http_client.get = AsyncMock(return_value=_tags_response(["qwen2.5:1.5b"]))
    http_client.post = AsyncMock(side_effect=http_error)

    client = OllamaClient(
        client=http_client,
        model="qwen2.5:1.5b",
        max_retries=2,
        base_url="http://ollama.local",
    )
    with caplog.at_level("WARNING"), pytest.raises(OllamaModelNotFoundError, match="HTTP 404"):
        await client.generate("prompt")

    assert http_client.post.await_count == 1
    assert any("ollama_model_not_found" in record.getMessage() for record in caplog.records)
    assert not any("ollama_transient_failure" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_http_404_uses_fallback_model_once() -> None:
    request = httpx.Request("POST", "http://ollama.local/api/generate")
    not_found = httpx.Response(
        404,
        request=request,
        text='{"error":"model \'missing:1b\' not found"}',
    )
    success = MagicMock()
    success.raise_for_status = MagicMock()
    success.json.return_value = {
        "model": "llama3.2:3b",
        "response": "ok",
        "done": True,
    }

    http_client = AsyncMock()
    http_client.get = AsyncMock(
        side_effect=[
            _tags_response(["missing:1b"]),
            _tags_response(["llama3.2:3b"]),
        ]
    )
    http_client.post = AsyncMock(
        side_effect=[
            httpx.HTTPStatusError("Not Found", request=request, response=not_found),
            success,
        ]
    )

    client = OllamaClient(
        client=http_client,
        model="missing:1b",
        max_retries=2,
        base_url="http://ollama.local",
    )
    result = await client.generate("prompt")

    assert result.response == "ok"
    assert client.model == "llama3.2:3b"
    assert http_client.post.await_count == 2


@pytest.mark.asyncio
async def test_ollama_client_requests_json_format() -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "model": "qwen2.5:7b",
        "response": json.dumps(
            {
                "subject": "Hi",
                "opening": "Hello",
                "body": "Body",
                "cta": "Call?",
            }
        ),
        "done": True,
    }

    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=mock_response)

    client = OllamaClient(client=http_client, max_retries=0, base_url="http://ollama.local")
    client._model_verified = True
    await client.generate("test prompt")

    payload = http_client.post.await_args.kwargs["json"]
    assert payload["format"] == "json"
    assert payload["options"]["temperature"] == client.temperature
    assert payload["options"]["num_predict"] == client.max_tokens


@pytest.mark.asyncio
async def test_fallback_email_content_unchanged() -> None:
    client = AsyncMock()
    client.generate = AsyncMock(side_effect=RuntimeError("boom"))
    client.model = "qwen2.5:7b"

    lead = make_lead()
    personalized = CompanyPersonalizationService().generate(lead)
    email = await AIEmailGenerator(client=client).generate_email(lead)

    assert email.generation_source == "fallback"
    assert email.subject
    assert "quick thought on" not in email.subject.lower()
    assert personalized.company_name.split()[0] in email.subject or personalized.company_name in (
        email.subject
    )
    assert email.opening in {personalized.personalized_opening, "Hi Ada,"}
    assert email.cta == personalized.cta_recommendation
    assert personalized.mobile_app_opportunity in email.body
    assert "Detected stack" not in email.body
    assert "technical partnership" not in email.body.lower()
    assert client.generate.await_count == 2


@pytest.mark.asyncio
async def test_real_ollama_generation_if_available() -> None:
    from app.core.config import settings

    probe_url = f"{settings.ollama_url.rstrip('/')}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=5.0) as probe_client:
            response = await probe_client.get(probe_url)
            if response.status_code != 200:
                pytest.skip("Ollama not available locally")
            models = response.json().get("models") or []
            if not models:
                pytest.skip("Ollama has no installed models")
    except Exception:
        pytest.skip("Ollama not available locally")

    client = OllamaClient(timeout=min(settings.ollama_timeout, 90.0))
    generator = AIEmailGenerator(client=client)
    email = await generator.generate_email(make_lead())

    assert email.generation_source == "ollama"
    assert email.errors == []
    assert email.subject.strip()
    assert email.opening.strip()
    assert email.body.strip()
    assert email.cta.strip()
    assert "```" not in email.subject
    assert "```" not in email.body
    assert email.response_time_ms <= 90_000
