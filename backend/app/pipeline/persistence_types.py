from __future__ import annotations

from pydantic import BaseModel, Field


class PersistenceResult(BaseModel):
    company_id: str | None = None
    company_created: bool = False
    company_updated: bool = False
    contacts_created: int = 0
    contacts_updated: int = 0
    contacts_skipped: int = 0
    decision_makers_created: int = 0
    decision_makers_updated: int = 0
    decision_makers_skipped: int = 0
    founders_created: int = 0
    founders_updated: int = 0
    founders_skipped: int = 0
    hiring_opportunities_created: int = 0
    hiring_opportunities_updated: int = 0
    hiring_opportunities_skipped: int = 0
    company_intelligence_saved: bool = False
    opportunity_score_saved: bool = False
    email_pattern_saved: bool = False
    duplicates_skipped: int = 0
    skipped: bool = False
    skip_reason: str | None = None
    errors: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0
