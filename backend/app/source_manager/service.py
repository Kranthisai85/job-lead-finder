from app.core.config import settings
from app.core.logger import get_logger
from app.source_manager.manager import StartupSourceManager
from app.source_manager.types import SourceCollectionReport


class SourceCollectionService:
    """Public entrypoint for multi-source startup collection."""

    def __init__(self, manager: StartupSourceManager | None = None) -> None:
        self.manager = manager or StartupSourceManager()
        self.logger = get_logger(__name__)

    async def collect_all(self) -> SourceCollectionReport:
        enabled_sources = self._parse_enabled_sources(settings.enabled_sources)
        self.logger.info(
            "service=SourceCollectionService action=collect_all sources=%s",
            enabled_sources,
        )
        return await self.collect(enabled_sources)

    async def collect(self, enabled_sources: list[str]) -> SourceCollectionReport:
        self.logger.info(
            "service=SourceCollectionService action=collect sources=%s",
            enabled_sources,
        )
        report = await self.manager.collect(enabled_sources)
        self.logger.info(
            (
                "service=SourceCollectionService action=completed "
                "collectors_run=%d total_found=%d unique=%d duration_ms=%.2f"
            ),
            len(report.collectors_run),
            report.total_found,
            len(report.unique_companies),
            report.execution_time_ms,
        )
        return report

    @staticmethod
    def _parse_enabled_sources(raw: str) -> list[str]:
        return [item.strip().lower() for item in raw.split(",") if item.strip()]
