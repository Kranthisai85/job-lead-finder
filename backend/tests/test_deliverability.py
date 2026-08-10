from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.contact_discovery.validators import is_generic_inbox_email, is_outbound_safe_email
from app.email_queue.deliverability import domain_accepts_mail, email_domain
from app.lead_generation.orchestrator import LeadGenerationOrchestrator
from app.pipeline.types import CompleteLead, ProcessingMetadata, StartupSeed
from app.contact_discovery.types import ContactCandidate, ContactDiscoveryReport


def test_generic_inbox_emails_are_rejected_for_outbound() -> None:
    assert is_generic_inbox_email("hello@luphra.com") is True
    assert is_generic_inbox_email("info@acme.com") is True
    assert is_generic_inbox_email("support@acme.com") is True
    assert is_outbound_safe_email("hello@luphra.com") is False
    assert is_outbound_safe_email("founder@acme.com") is True
    assert is_outbound_safe_email("ada@acme.example") is True


def test_best_recipient_skips_generic_inbox() -> None:
    lead = CompleteLead(
        startup=StartupSeed(name="Luphra", website="https://luphra.com", source="test"),
        contacts=ContactDiscoveryReport(
            url="https://luphra.com",
            contacts=[
                ContactCandidate(
                    full_name=None,
                    email="hello@luphra.com",
                    confidence=0.9,
                )
            ],
            emails=["hello@luphra.com", "ada@luphra.com"],
            contact_count=1,
        ),
        processing=ProcessingMetadata(success=True),
    )
    recipient = LeadGenerationOrchestrator._best_recipient(lead)
    assert recipient is not None
    assert recipient["email"] == "ada@luphra.com"


def test_best_recipient_returns_none_when_only_generic() -> None:
    lead = CompleteLead(
        startup=StartupSeed(name="Luphra", website="https://luphra.com", source="test"),
        contacts=ContactDiscoveryReport(
            url="https://luphra.com",
            emails=["hello@luphra.com", "info@luphra.com"],
            contact_count=0,
        ),
        processing=ProcessingMetadata(success=True),
    )
    assert LeadGenerationOrchestrator._best_recipient(lead) is None


@pytest.mark.asyncio
async def test_domain_accepts_mail_for_example_tld() -> None:
    assert email_domain("ada@acme.example") == "acme.example"
    assert await domain_accepts_mail("acme.example") is True


@pytest.mark.asyncio
async def test_domain_accepts_mail_false_without_mx() -> None:
    from unittest.mock import MagicMock

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"Status": 0, "Answer": []}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False

    with patch("app.email_queue.deliverability.httpx.AsyncClient", return_value=mock_client):
        assert await domain_accepts_mail("no-mail-box.com") is False
