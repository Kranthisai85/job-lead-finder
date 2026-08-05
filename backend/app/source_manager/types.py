from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.collectors.types import CompanyLead


class CollectorStatistics(BaseModel):
    collector_name: str
    companies_collected: int = 0
    duration_ms: float = 0.0
    success: bool = True
    error: str | None = None


class CollectorExecution(BaseModel):
    collector_name: str
    started_at: datetime
    finished_at: datetime | None = None
    companies_collected: int = 0
    duration_ms: float = 0.0
    success: bool = True
    error: str | None = None


class SourceCollectionReport(BaseModel):
    collectors_run: list[str] = Field(default_factory=list)
    total_found: int = 0
    duplicates_removed: int = 0
    unique_companies: list[CompanyLead] = Field(default_factory=list)
    execution_time_ms: float = 0.0
    collector_statistics: list[CollectorStatistics] = Field(default_factory=list)
    collector_executions: list[CollectorExecution] = Field(default_factory=list)
