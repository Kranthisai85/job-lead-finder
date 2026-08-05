"""Founder Enrichment public exports (lazy to avoid import cycles)."""

from typing import Any

__all__ = [
    "FounderEnrichmentReport",
    "FounderEnrichmentService",
    "FounderProfile",
    "FounderProfileDocument",
    "FounderProfileRepository",
]


def __getattr__(name: str) -> Any:
    if name in {
        "FounderEnrichmentReport",
        "FounderProfile",
        "FounderProfileDocument",
    }:
        from app.founder_enrichment.models import (
            FounderEnrichmentReport,
            FounderProfile,
            FounderProfileDocument,
        )

        return {
            "FounderEnrichmentReport": FounderEnrichmentReport,
            "FounderProfile": FounderProfile,
            "FounderProfileDocument": FounderProfileDocument,
        }[name]
    if name == "FounderProfileRepository":
        from app.founder_enrichment.repository import FounderProfileRepository

        return FounderProfileRepository
    if name == "FounderEnrichmentService":
        from app.founder_enrichment.service import FounderEnrichmentService

        return FounderEnrichmentService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
