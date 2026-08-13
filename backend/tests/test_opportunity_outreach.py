"""Opportunity signal + hiring inbox tests."""

from __future__ import annotations

from app.contact_discovery.validators import (
    is_hiring_inbox_email,
    is_outbound_safe_email,
)
from app.hiring_detection.types import HiringDetectionReport, HiringOpportunity
from app.mobile_detection.types import MobileAppDetectionResult
from app.outreach.opportunity import OutreachMode, classify_outreach_mode
from app.pipeline.types import CompleteLead, StartupSeed


def _lead(**kwargs) -> CompleteLead:
    base = {
        "startup": StartupSeed(
            name="Acme",
            website="https://acme.example",
            description="Acme builds tools",
            source="test",
        )
    }
    base.update(kwargs)
    return CompleteLead(**base)


def test_hiring_inbox_allowed_when_flag_on() -> None:
    assert is_hiring_inbox_email("jobs@acme.example") is True
    assert is_outbound_safe_email("jobs@acme.example") is False
    assert is_outbound_safe_email("jobs@acme.example", allow_hiring_inboxes=True) is True
    assert is_outbound_safe_email("hello@acme.example", allow_hiring_inboxes=True) is False


def test_classify_hiring_mode_for_flutter_jobs() -> None:
    lead = _lead(
        hiring_report=HiringDetectionReport(
            url="https://acme.example/careers",
            jobs_found=1,
            flutter_jobs=1,
            opportunities=[
                HiringOpportunity(title="Flutter Developer", confidence=0.9),
            ],
        )
    )
    assert classify_outreach_mode(lead) == OutreachMode.HIRING


def test_classify_freelance_when_no_mobile_app() -> None:
    lead = _lead(
        mobile_report=MobileAppDetectionResult(
            has_mobile_app=False,
            confidence=0.8,
        )
    )
    assert classify_outreach_mode(lead) == OutreachMode.FREELANCE


def test_classify_none_when_already_has_mobile_and_no_hiring() -> None:
    lead = _lead(
        mobile_report=MobileAppDetectionResult(
            has_mobile_app=True,
            confidence=0.9,
            android_detected=True,
        )
    )
    assert classify_outreach_mode(lead) == OutreachMode.NONE
