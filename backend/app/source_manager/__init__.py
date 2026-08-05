"""Multi-source startup collection orchestration."""

from app.source_manager import sources  # noqa: F401 — registers source collectors
from app.source_manager.base import BaseSourceCollector
from app.source_manager.manager import StartupSourceManager
from app.source_manager.registry import SourceRegistry
from app.source_manager.service import SourceCollectionService
from app.source_manager.types import (
    CollectorExecution,
    CollectorStatistics,
    SourceCollectionReport,
)

__all__ = [
    "BaseSourceCollector",
    "CollectorExecution",
    "CollectorStatistics",
    "SourceCollectionReport",
    "SourceCollectionService",
    "SourceRegistry",
    "StartupSourceManager",
]
