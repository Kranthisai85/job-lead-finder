from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ScheduledJobResult(BaseModel):
    job_name: str
    success: bool = True
    processed: int = 0
    failed: int = 0
    duration_ms: float = 0.0
    errors: list[str] = Field(default_factory=list)
    details: dict[str, object] = Field(default_factory=dict)


class JobExecutionMetrics(BaseModel):
    job_name: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float = 0.0
    success: bool | None = None
    error: str | None = None
    last_execution: datetime | None = None
    next_execution: datetime | None = None


class SchedulerStatus(BaseModel):
    running: bool = False
    enabled: bool = False
    jobs: list[JobExecutionMetrics] = Field(default_factory=list)


class SchedulerState(BaseModel):
    last_collected_seeds_count: int = 0
