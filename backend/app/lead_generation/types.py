from __future__ import annotations

from pydantic import BaseModel, Field


class StageTiming(BaseModel):
    stage: str
    duration_ms: float = 0.0
    success: bool = True
    error: str | None = None


class LeadGenerationResult(BaseModel):
    company_name: str
    website: str
    success: bool = True
    persisted: bool = False
    qualified: bool = False
    email_generated: bool = False
    queued: bool = False
    company_id: str | None = None
    contact_id: str | None = None
    duration_ms: float = 0.0
    stage_timings: list[StageTiming] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class LeadGenerationStatistics(BaseModel):
    total_collected: int = 0
    processed: int = 0
    persisted: int = 0
    qualified: int = 0
    emails_generated: int = 0
    queued: int = 0
    failed: int = 0
    duration_ms: float = 0.0


class LeadGenerationReport(BaseModel):
    statistics: LeadGenerationStatistics = Field(default_factory=LeadGenerationStatistics)
    results: list[LeadGenerationResult] = Field(default_factory=list)
    stage_timings: list[StageTiming] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    success: bool = True
