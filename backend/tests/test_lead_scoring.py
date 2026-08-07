"""Focused unit tests for deterministic outbound lead scoring (Step 37)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.lead_scoring.scorer import (
    POINTS_AGENCY_OR_RECRUITMENT,
    POINTS_FOUNDER_OR_CONTACT,
    POINTS_MOBILE_APP_EXISTS,
    POINTS_NO_MOBILE_APP,
    POINTS_NO_USABLE_CONTACT,
    POINTS_VALID_EMAIL,
    clamp_score,
    is_queue_eligible,
    score_lead,
    status_for_score,
)
from app.lead_scoring.service import LeadScoringService
from app.lead_scoring.signals import extract_signals
from app.lead_scoring.types import LeadQualificationStatus, LeadScoreSignals
from app.personalization.generator import PersonalizationGenerator
from app.pipeline.types import StartupSeed
from tests.test_lead_generation import build_orchestrator
from tests.test_personalization import make_lead


def test_high_scoring_lead() -> None:
    result = score_lead(
        LeadScoreSignals(
            recently_launched=True,
            has_mobile_app=False,
            is_product_company=True,
            has_founder_or_contact=True,
            has_valid_email=True,
        )
    )
    assert result.score == 100
    assert result.status == LeadQualificationStatus.HIGH
    assert any("Recently launched" in reason for reason in result.reasons)


def test_medium_scoring_lead() -> None:
    # 25 + 20 + 15 + 10 = 70
    result = score_lead(
        LeadScoreSignals(
            has_mobile_app=False,
            is_product_company=True,
            has_founder_or_contact=True,
            has_valid_email=True,
        )
    )
    assert result.score == 70
    assert result.status == LeadQualificationStatus.MEDIUM


def test_low_scoring_lead() -> None:
    # no mobile (+25) + product (+20) + email (+10) = 55 → LOW
    result = score_lead(
        LeadScoreSignals(
            has_mobile_app=False,
            is_product_company=True,
            has_founder_or_contact=False,
            has_valid_email=True,
        )
    )
    assert result.score == 55
    assert result.status == LeadQualificationStatus.LOW


def test_rejected_lead() -> None:
    result = score_lead(
        LeadScoreSignals(
            has_mobile_app=True,
            is_agency_or_recruitment=True,
            is_generic_website=True,
            has_founder_or_contact=False,
            has_valid_email=False,
        )
    )
    assert result.score == 0
    assert result.status == LeadQualificationStatus.REJECT


def test_existing_mobile_app_negative_signal() -> None:
    result = score_lead(LeadScoreSignals(has_mobile_app=True, has_valid_email=True))
    assert POINTS_MOBILE_APP_EXISTS == -30
    assert any("Existing mobile app" in reason for reason in result.reasons)
    assert result.score == clamp_score(POINTS_MOBILE_APP_EXISTS + POINTS_VALID_EMAIL)


def test_no_mobile_app_positive_signal() -> None:
    result = score_lead(LeadScoreSignals(has_mobile_app=False))
    assert any(f"+{POINTS_NO_MOBILE_APP}" in reason for reason in result.reasons)
    # no mobile + no contact
    assert result.score == clamp_score(POINTS_NO_MOBILE_APP + POINTS_NO_USABLE_CONTACT)


def test_valid_email_signal() -> None:
    result = score_lead(LeadScoreSignals(has_valid_email=True))
    assert any(f"+{POINTS_VALID_EMAIL}" in reason for reason in result.reasons)


def test_no_email_does_not_receive_email_points() -> None:
    result = score_lead(LeadScoreSignals(has_valid_email=False, has_founder_or_contact=True))
    assert all("Valid email" not in reason for reason in result.reasons)
    assert result.score == POINTS_FOUNDER_OR_CONTACT


def test_founder_contact_signal() -> None:
    result = score_lead(LeadScoreSignals(has_founder_or_contact=True))
    assert any(f"+{POINTS_FOUNDER_OR_CONTACT}" in reason for reason in result.reasons)


def test_agency_recruitment_negative_signal() -> None:
    result = score_lead(LeadScoreSignals(is_agency_or_recruitment=True, has_valid_email=True))
    assert any("Agency/recruitment" in reason for reason in result.reasons)
    assert POINTS_AGENCY_OR_RECRUITMENT in (-30,)


def test_score_clamped_to_0_100() -> None:
    assert clamp_score(-50) == 0
    assert clamp_score(150) == 100
    high = score_lead(
        LeadScoreSignals(
            recently_launched=True,
            has_mobile_app=False,
            is_product_company=True,
            has_founder_or_contact=True,
            has_valid_email=True,
        )
    )
    assert high.score == 100
    low = score_lead(
        LeadScoreSignals(
            has_mobile_app=True,
            is_agency_or_recruitment=True,
            is_generic_website=True,
            has_founder_or_contact=False,
            has_valid_email=False,
        )
    )
    assert low.score == 0


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (100, LeadQualificationStatus.HIGH),
        (80, LeadQualificationStatus.HIGH),
        (79, LeadQualificationStatus.MEDIUM),
        (60, LeadQualificationStatus.MEDIUM),
        (59, LeadQualificationStatus.LOW),
        (40, LeadQualificationStatus.LOW),
        (39, LeadQualificationStatus.REJECT),
        (0, LeadQualificationStatus.REJECT),
    ],
)
def test_qualification_status_boundaries(score: int, expected: LeadQualificationStatus) -> None:
    assert status_for_score(score) == expected


def test_queue_eligibility_respects_min_lead_score() -> None:
    assert is_queue_eligible(60, min_lead_score=60) is True
    assert is_queue_eligible(59, min_lead_score=60) is False
    assert is_queue_eligible(80, min_lead_score=70) is True
    assert is_queue_eligible(69, min_lead_score=70) is False
    service = LeadScoringService(min_lead_score=60)
    assert (
        service.is_eligible(
            score_lead(
                LeadScoreSignals(
                    has_mobile_app=False,
                    is_product_company=True,
                    has_founder_or_contact=True,
                    has_valid_email=True,
                )
            )
        )
        is True
    )


def test_extract_signals_from_make_lead() -> None:
    lead = make_lead(has_mobile_app=False, with_contacts=True)
    signals = extract_signals(lead)
    assert signals.has_mobile_app is False
    assert signals.has_valid_email is True
    assert signals.has_founder_or_contact is True
    assert signals.is_product_company is True


def test_extract_agency_signal() -> None:
    lead = make_lead(description="We are a digital agency offering client projects")
    assert lead.company_profile is not None
    lead.company_profile = lead.company_profile.model_copy(update={"business_category": "Agencies"})
    signals = extract_signals(lead)
    assert signals.is_agency_or_recruitment is True


def test_flutter_evidence_independent_of_lead_score() -> None:
    """is_flutter_lead must remain evidence-based and separate from outbound score."""
    lead = make_lead(has_mobile_app=False, technologies=["React"], qualified=True)
    assert PersonalizationGenerator.has_explicit_flutter_evidence(lead) is False
    result = LeadScoringService().score(lead)
    assert result.score >= 60
    assert result.status != LeadQualificationStatus.REJECT

    flutter_lead = make_lead(has_mobile_app=True, technologies=["Flutter"])
    assert PersonalizationGenerator.has_explicit_flutter_evidence(flutter_lead) is True
    # Mobile app still applies negative outbound signal even when Flutter evidence is true.
    flutter_score = LeadScoringService().score(flutter_lead)
    assert any("Existing mobile app" in reason for reason in flutter_score.reasons)


@pytest.mark.asyncio
async def test_queue_skips_below_min_lead_score() -> None:
    weak = make_lead(has_mobile_app=True, with_contacts=True, company_name="WeakCo")
    weak.startup = StartupSeed(
        name="WeakCo",
        website="https://weak.vercel.app",
        description="recruitment staffing agency for hire",
        source="test",
    )
    if weak.company_profile is not None:
        weak.company_profile = weak.company_profile.model_copy(
            update={
                "business_category": "Agencies",
                "product_type": "Consulting",
                "industry": "Recruitment",
            }
        )

    pipeline_service = AsyncMock()
    pipeline_service.process = AsyncMock(return_value=weak)
    harness = build_orchestrator(pipeline_service=pipeline_service)
    harness.orchestrator.lead_scoring_service = LeadScoringService(min_lead_score=60)

    report = await harness.orchestrator.run(limit=1)
    assert report.results[0].queued is False
    assert report.statistics.queued == 0
    harness.enqueue_mock.assert_not_called()
    assert any("MIN_LEAD_SCORE" in warning for warning in report.results[0].warnings)


@pytest.mark.asyncio
async def test_queue_skips_no_recipient_even_when_score_high() -> None:
    lead = make_lead(has_mobile_app=False, with_contacts=False, company_name="NoEmailCo")
    lead.startup.source = "producthunt"
    pipeline_service = AsyncMock()
    pipeline_service.process = AsyncMock(return_value=lead)
    harness = build_orchestrator(pipeline_service=pipeline_service)

    report = await harness.orchestrator.run(limit=1)
    assert report.results[0].email_generated is True
    assert report.results[0].queued is False
    harness.enqueue_mock.assert_not_called()
    assert any("No contact email" in warning for warning in report.results[0].warnings)


@pytest.mark.asyncio
async def test_runtime_qualification_log_includes_status_and_eligible(
    caplog: pytest.LogCaptureFixture,
) -> None:
    harness = build_orchestrator()
    with caplog.at_level("INFO"):
        await harness.orchestrator.run(limit=1)

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "[QUALIFICATION] company=" in messages
    assert "status=" in messages
    assert "eligible=" in messages
    assert "reasons=" in messages
    assert "[FLUTTER] company=" in messages
    assert "[QUEUE] company=" in messages and "status=PENDING" in messages
