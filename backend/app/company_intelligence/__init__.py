"""Company Intelligence v2 public exports (lazy to avoid import cycles)."""

from typing import Any

__all__ = [
    "CompanyIntelligenceDocument",
    "CompanyIntelligenceReport",
    "CompanyIntelligenceRepository",
    "CompanyIntelligenceService",
]


def __getattr__(name: str) -> Any:
    if name in {"CompanyIntelligenceDocument", "CompanyIntelligenceReport"}:
        from app.company_intelligence.models import (
            CompanyIntelligenceDocument,
            CompanyIntelligenceReport,
        )

        return {
            "CompanyIntelligenceDocument": CompanyIntelligenceDocument,
            "CompanyIntelligenceReport": CompanyIntelligenceReport,
        }[name]
    if name == "CompanyIntelligenceRepository":
        from app.company_intelligence.repository import CompanyIntelligenceRepository

        return CompanyIntelligenceRepository
    if name == "CompanyIntelligenceService":
        from app.company_intelligence.service import CompanyIntelligenceService

        return CompanyIntelligenceService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
