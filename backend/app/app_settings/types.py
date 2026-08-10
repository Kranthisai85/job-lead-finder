"""App settings types."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    skip_duplicate_companies: bool = True


class AppSettingsUpdate(BaseModel):
    skip_duplicate_companies: bool = Field(
        default=True,
        description=(
            "When true, skip companies (and recipient emails) that already exist "
            "in the email queue as PENDING, SKIPPED, APPROVED, SENT, etc."
        ),
    )
