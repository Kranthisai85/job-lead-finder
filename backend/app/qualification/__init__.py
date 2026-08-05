"""Qualification package public exports."""

from typing import Any

from app.qualification.types import QualificationLevel, QualificationResult, RuleEvaluation

__all__ = [
    "QualificationEngine",
    "QualificationLevel",
    "QualificationResult",
    "QualificationScoringEngine",
    "QualificationService",
    "RuleEvaluation",
    "build_default_engine",
    "build_default_scoring_engine",
]


def __getattr__(name: str) -> Any:
    if name in {"QualificationEngine", "build_default_engine"}:
        from app.qualification.engine import QualificationEngine, build_default_engine

        return {
            "QualificationEngine": QualificationEngine,
            "build_default_engine": build_default_engine,
        }[name]
    if name in {"QualificationScoringEngine", "build_default_scoring_engine"}:
        from app.qualification.scoring_engine import (
            QualificationScoringEngine,
            build_default_scoring_engine,
        )

        return {
            "QualificationScoringEngine": QualificationScoringEngine,
            "build_default_scoring_engine": build_default_scoring_engine,
        }[name]
    if name == "QualificationService":
        from app.qualification.service import QualificationService

        return QualificationService
    if name == "QualificationLevel":
        return QualificationLevel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
