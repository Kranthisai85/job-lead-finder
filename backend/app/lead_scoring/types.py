"""Types for deterministic outbound lead scoring (Step 37)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class LeadQualificationStatus(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    REJECT = "REJECT"


class LeadScoreSignals(BaseModel):
    """Evidence flags — award points only when True (or explicit False for mobile)."""

    recently_launched: bool = False
    has_mobile_app: bool | None = None
    is_product_company: bool = False
    has_founder_or_contact: bool = False
    has_valid_email: bool = False
    is_agency_or_recruitment: bool = False
    is_generic_website: bool = False


class LeadScoreResult(BaseModel):
    score: int = Field(ge=0, le=100)
    status: LeadQualificationStatus
    reasons: list[str] = Field(default_factory=list)

    @property
    def qualification_score(self) -> int:
        return self.score

    @property
    def qualification_status(self) -> str:
        return self.status.value

    @property
    def qualification_reasons(self) -> list[str]:
        return list(self.reasons)
