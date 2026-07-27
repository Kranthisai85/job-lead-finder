from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class JobContext(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid4()))
    job_type: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobResult(BaseModel):
    success: bool
    processed: int = 0
    failed: int = 0
    duration_ms: float = 0.0
    errors: list[str] = Field(default_factory=list)
