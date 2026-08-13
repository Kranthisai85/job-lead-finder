"""Outreach mode helpers (hiring vs freelance)."""

from app.outreach.opportunity import (
    OutreachMode,
    classify_outreach_mode,
    has_opportunity_signal,
    hiring_roles_summary,
)

__all__ = [
    "OutreachMode",
    "classify_outreach_mode",
    "has_opportunity_signal",
    "hiring_roles_summary",
]
