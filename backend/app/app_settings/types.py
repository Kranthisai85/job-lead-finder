"""App settings types."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    skip_duplicate_companies: bool = True
    scheduler_hour: int = Field(default=9, ge=0, le=23)
    scheduler_minute: int = Field(default=0, ge=0, le=59)
    # Read-only for UI display; configured via env (SCHEDULER_TIMEZONE).
    scheduler_timezone: str = "Asia/Kolkata"


class AppSettingsUpdate(BaseModel):
    skip_duplicate_companies: bool = Field(
        default=True,
        description=(
            "When true, skip companies/recipients already PENDING, APPROVED, "
            "READY_TO_SEND, SENDING, or SENT. SKIPPED/FAILED may be retried."
        ),
    )
    scheduler_hour: int = Field(
        default=9,
        ge=0,
        le=23,
        description="Daily lead-generation run hour (0–23) in scheduler_timezone.",
    )
    scheduler_minute: int = Field(
        default=0,
        ge=0,
        le=59,
        description="Daily lead-generation run minute (0–59).",
    )
