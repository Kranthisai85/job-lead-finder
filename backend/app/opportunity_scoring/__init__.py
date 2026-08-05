"""Opportunity Scoring Engine public exports (lazy to avoid import cycles)."""

from typing import Any

__all__ = [
    "DEFAULT_OPPORTUNITY_CONFIG",
    "DEFAULT_WEIGHTS",
    "OpportunityScoreDocument",
    "OpportunityScoreReport",
    "OpportunityScoreRepository",
    "OpportunityScoringConfig",
    "OpportunityScoringService",
    "OpportunityWeights",
]


def __getattr__(name: str) -> Any:
    if name in {"OpportunityScoreDocument", "OpportunityScoreReport"}:
        from app.opportunity_scoring.models import (
            OpportunityScoreDocument,
            OpportunityScoreReport,
        )

        return {
            "OpportunityScoreDocument": OpportunityScoreDocument,
            "OpportunityScoreReport": OpportunityScoreReport,
        }[name]
    if name == "OpportunityScoreRepository":
        from app.opportunity_scoring.repository import OpportunityScoreRepository

        return OpportunityScoreRepository
    if name == "OpportunityScoringService":
        from app.opportunity_scoring.service import OpportunityScoringService

        return OpportunityScoringService
    if name in {
        "DEFAULT_OPPORTUNITY_CONFIG",
        "DEFAULT_WEIGHTS",
        "OpportunityScoringConfig",
        "OpportunityWeights",
    }:
        from app.opportunity_scoring.weights import (
            DEFAULT_OPPORTUNITY_CONFIG,
            DEFAULT_WEIGHTS,
            OpportunityScoringConfig,
            OpportunityWeights,
        )

        return {
            "DEFAULT_OPPORTUNITY_CONFIG": DEFAULT_OPPORTUNITY_CONFIG,
            "DEFAULT_WEIGHTS": DEFAULT_WEIGHTS,
            "OpportunityScoringConfig": OpportunityScoringConfig,
            "OpportunityWeights": OpportunityWeights,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
