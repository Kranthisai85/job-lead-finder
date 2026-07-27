from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class CompanyLead(BaseModel):
    name: str
    website: str
    description: str | None = None
    source: str
    tags: list[str] = Field(default_factory=list)
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class CollectorRunResult(BaseModel):
    collector_name: str
    collected_count: int
    normalized_count: int
    valid_count: int
    saved_count: int
    duration_ms: float
