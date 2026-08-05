"""Opportunity scoring DTOs and persistence document."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from pymongo import IndexModel

from app.models.base import BaseDocument

OpportunityPriority = Literal["Critical", "High", "Medium", "Low", "Very Low"]

OpportunityLevel = Literal[
    "Exceptional",
    "Strong",
    "Moderate",
    "Weak",
    "Negligible",
]

RecommendedAction = Literal[
    "Send immediately",
    "Send founder email",
    "Wait",
    "Research manually",
    "Ignore",
]

PRIORITIES: tuple[str, ...] = ("Critical", "High", "Medium", "Low", "Very Low")
OPPORTUNITY_LEVELS: tuple[str, ...] = (
    "Exceptional",
    "Strong",
    "Moderate",
    "Weak",
    "Negligible",
)
RECOMMENDED_ACTIONS: tuple[str, ...] = (
    "Send immediately",
    "Send founder email",
    "Wait",
    "Research manually",
    "Ignore",
)


class OpportunityScoreReport(BaseModel):
    """Sales-priority opportunity score (distinct from qualification quality score)."""

    url: str = ""
    overall_score: int = Field(default=0, ge=0, le=100)
    priority: str = "Very Low"
    opportunity_level: str = "Negligible"
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommended_action: str = "Ignore"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    score_breakdown: dict[str, int] = Field(default_factory=dict)


class OpportunityScoreDocument(BaseDocument):
    """Persisted opportunity score — separate from Company / Qualification models."""

    company_id: str
    url: str | None = None
    overall_score: int = 0
    priority: str | None = None
    opportunity_level: str | None = None
    reasons: list[str] = []
    warnings: list[str] = []
    recommended_action: str | None = None
    confidence: float | None = None
    score_breakdown: dict[str, int] = {}

    class Settings:
        name = "opportunity_scores"
        indexes = [
            IndexModel([("company_id", 1)], unique=True),
            IndexModel([("priority", 1)]),
            IndexModel([("overall_score", -1)]),
            IndexModel([("created_at", -1)]),
        ]
