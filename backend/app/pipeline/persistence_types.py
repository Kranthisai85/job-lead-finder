from __future__ import annotations

from pydantic import BaseModel, Field


class PersistenceResult(BaseModel):
    company_id: str | None = None
    company_created: bool = False
    company_updated: bool = False
    contacts_created: int = 0
    contacts_updated: int = 0
    contacts_skipped: int = 0
    email_pattern_saved: bool = False
    duplicates_skipped: int = 0
    skipped: bool = False
    skip_reason: str | None = None
    errors: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0
