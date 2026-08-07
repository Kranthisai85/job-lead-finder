"""Deterministic outbound lead scorer — no LLM, no I/O."""

from __future__ import annotations

from app.lead_scoring.types import LeadQualificationStatus, LeadScoreResult, LeadScoreSignals

# Positive signals
POINTS_RECENTLY_LAUNCHED = 30
POINTS_NO_MOBILE_APP = 25
POINTS_PRODUCT_COMPANY = 20
POINTS_FOUNDER_OR_CONTACT = 15
POINTS_VALID_EMAIL = 10

# Negative signals
POINTS_MOBILE_APP_EXISTS = -30
POINTS_AGENCY_OR_RECRUITMENT = -30
POINTS_GENERIC_WEBSITE = -20
POINTS_NO_USABLE_CONTACT = -20


def clamp_score(raw: int) -> int:
    return max(0, min(100, raw))


def status_for_score(score: int) -> LeadQualificationStatus:
    if score >= 80:
        return LeadQualificationStatus.HIGH
    if score >= 60:
        return LeadQualificationStatus.MEDIUM
    if score >= 40:
        return LeadQualificationStatus.LOW
    return LeadQualificationStatus.REJECT


def is_queue_eligible(score: int, *, min_lead_score: int) -> bool:
    return score >= min_lead_score


def score_lead(signals: LeadScoreSignals) -> LeadScoreResult:
    """Compute clamped score, band, and human-readable reason strings."""
    total = 0
    reasons: list[str] = []

    if signals.recently_launched:
        total += POINTS_RECENTLY_LAUNCHED
        reasons.append(f"Recently launched / startup signal (+{POINTS_RECENTLY_LAUNCHED})")

    if signals.has_mobile_app is False:
        total += POINTS_NO_MOBILE_APP
        reasons.append(f"No mobile app detected (+{POINTS_NO_MOBILE_APP})")
    elif signals.has_mobile_app is True:
        total += POINTS_MOBILE_APP_EXISTS
        reasons.append(f"Existing mobile app detected ({POINTS_MOBILE_APP_EXISTS})")

    if signals.is_product_company:
        total += POINTS_PRODUCT_COMPANY
        reasons.append(f"Product/software/startup company (+{POINTS_PRODUCT_COMPANY})")

    if signals.has_founder_or_contact:
        total += POINTS_FOUNDER_OR_CONTACT
        reasons.append(f"Founder/contact person discovered (+{POINTS_FOUNDER_OR_CONTACT})")

    if signals.has_valid_email:
        total += POINTS_VALID_EMAIL
        reasons.append(f"Valid email discovered (+{POINTS_VALID_EMAIL})")

    if signals.is_agency_or_recruitment:
        total += POINTS_AGENCY_OR_RECRUITMENT
        reasons.append(f"Agency/recruitment lead ({POINTS_AGENCY_OR_RECRUITMENT})")

    if signals.is_generic_website:
        total += POINTS_GENERIC_WEBSITE
        reasons.append(f"Generic/non-business website ({POINTS_GENERIC_WEBSITE})")

    if not signals.has_valid_email and not signals.has_founder_or_contact:
        total += POINTS_NO_USABLE_CONTACT
        reasons.append(f"No usable contact ({POINTS_NO_USABLE_CONTACT})")

    score = clamp_score(total)
    return LeadScoreResult(score=score, status=status_for_score(score), reasons=reasons)
