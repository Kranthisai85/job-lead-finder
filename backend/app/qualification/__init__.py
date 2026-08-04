"""Lead qualification engine."""

from typing import Any

from app.qualification.types import QualificationResult, RuleEvaluation

__all__ = [
    "QualificationEngine",
    "QualificationResult",
    "QualificationService",
    "RuleEvaluation",
    "build_default_engine",
]


def __getattr__(name: str) -> Any:
    if name in {"QualificationEngine", "build_default_engine"}:
        from app.qualification.engine import QualificationEngine, build_default_engine

        return {
            "QualificationEngine": QualificationEngine,
            "build_default_engine": build_default_engine,
        }[name]
    if name == "QualificationService":
        from app.qualification.service import QualificationService

        return QualificationService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
