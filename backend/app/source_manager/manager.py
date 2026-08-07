from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from time import perf_counter

from app.collectors.types import CompanyLead
from app.core.config import settings
from app.core.logger import get_logger
from app.source_manager.registry import SourceRegistry
from app.source_manager.types import CollectorExecution, CollectorStatistics, SourceCollectionReport
from app.utils.url import canonical_lead_website, website_identity


class StartupSourceManager:
    """Orchestrates source collectors sequentially and merges results."""

    def __init__(
        self,
        *,
        registry: type[SourceRegistry] = SourceRegistry,
        collection_timeout: float | None = None,
        max_collectors: int | None = None,
    ) -> None:
        self.registry = registry
        self.collection_timeout = (
            collection_timeout if collection_timeout is not None else settings.collection_timeout
        )
        self.max_collectors = (
            max_collectors if max_collectors is not None else settings.max_collectors
        )
        self.logger = get_logger(__name__)

    async def collect(self, enabled_sources: list[str]) -> SourceCollectionReport:
        started = perf_counter()
        sources = self._resolve_sources(enabled_sources)
        all_leads: list[CompanyLead] = []
        statistics: list[CollectorStatistics] = []
        executions: list[CollectorExecution] = []

        self.logger.info(
            "source_manager_started collectors=%s timeout=%.1f max_collectors=%d",
            sources,
            self.collection_timeout,
            self.max_collectors,
        )

        for source_name in sources:
            execution_started = datetime.now(timezone.utc)
            stage_started = perf_counter()
            self.logger.info("collector=%s status=started", source_name)

            try:
                collector = self.registry.create(source_name)
                leads = await asyncio.wait_for(
                    collector.collect_leads(),
                    timeout=self.collection_timeout,
                )
                duration_ms = round((perf_counter() - stage_started) * 1000, 2)
                finished_at = datetime.now(timezone.utc)

                all_leads.extend(leads)
                statistics.append(
                    CollectorStatistics(
                        collector_name=source_name,
                        companies_collected=len(leads),
                        duration_ms=duration_ms,
                        success=True,
                    )
                )
                executions.append(
                    CollectorExecution(
                        collector_name=source_name,
                        started_at=execution_started,
                        finished_at=finished_at,
                        companies_collected=len(leads),
                        duration_ms=duration_ms,
                        success=True,
                    )
                )
                self.logger.info(
                    "collector=%s status=completed companies_collected=%d duration_ms=%.2f",
                    source_name,
                    len(leads),
                    duration_ms,
                )
            except TimeoutError as exc:
                duration_ms = round((perf_counter() - stage_started) * 1000, 2)
                finished_at = datetime.now(timezone.utc)
                error = (
                    str(exc).strip() or f"collection timed out after {self.collection_timeout:.0f}s"
                )
                statistics.append(
                    CollectorStatistics(
                        collector_name=source_name,
                        companies_collected=0,
                        duration_ms=duration_ms,
                        success=False,
                        error=error,
                    )
                )
                executions.append(
                    CollectorExecution(
                        collector_name=source_name,
                        started_at=execution_started,
                        finished_at=finished_at,
                        companies_collected=0,
                        duration_ms=duration_ms,
                        success=False,
                        error=error,
                    )
                )
                self.logger.warning(
                    "collector=%s status=failed error=%s duration_ms=%.2f",
                    source_name,
                    error,
                    duration_ms,
                )
            except Exception as exc:
                duration_ms = round((perf_counter() - stage_started) * 1000, 2)
                finished_at = datetime.now(timezone.utc)
                error = str(exc).strip() or type(exc).__name__
                statistics.append(
                    CollectorStatistics(
                        collector_name=source_name,
                        companies_collected=0,
                        duration_ms=duration_ms,
                        success=False,
                        error=error,
                    )
                )
                executions.append(
                    CollectorExecution(
                        collector_name=source_name,
                        started_at=execution_started,
                        finished_at=finished_at,
                        companies_collected=0,
                        duration_ms=duration_ms,
                        success=False,
                        error=error,
                    )
                )
                self.logger.warning(
                    "collector=%s status=failed error=%s duration_ms=%.2f",
                    source_name,
                    error,
                    duration_ms,
                )

        unique_companies, duplicates_removed = self._dedupe_leads(all_leads)
        execution_time_ms = round((perf_counter() - started) * 1000, 2)

        self.logger.info(
            (
                "source_manager_completed collectors_run=%d total_found=%d "
                "duplicates_removed=%d unique_companies=%d duration_ms=%.2f"
            ),
            len(sources),
            len(all_leads),
            duplicates_removed,
            len(unique_companies),
            execution_time_ms,
        )

        return SourceCollectionReport(
            collectors_run=sources,
            total_found=len(all_leads),
            duplicates_removed=duplicates_removed,
            unique_companies=unique_companies,
            execution_time_ms=execution_time_ms,
            collector_statistics=statistics,
            collector_executions=executions,
        )

    def _resolve_sources(self, enabled_sources: list[str]) -> list[str]:
        if not enabled_sources:
            return []

        resolved: list[str] = []
        for source in enabled_sources:
            normalized = source.strip().lower()
            if not normalized or normalized in resolved:
                continue
            if normalized not in self.registry.list():
                raise KeyError(f"Source collector '{source}' is not registered")
            resolved.append(normalized)

        return resolved[: self.max_collectors]

    @staticmethod
    def _dedupe_leads(leads: list[CompanyLead]) -> tuple[list[CompanyLead], int]:
        seen: set[str] = set()
        unique: list[CompanyLead] = []
        duplicates_removed = 0

        for lead in leads:
            identity = website_identity(lead.website)
            if not identity:
                duplicates_removed += 1
                continue
            if identity in seen:
                duplicates_removed += 1
                continue
            seen.add(identity)
            unique.append(lead.model_copy(update={"website": canonical_lead_website(lead.website)}))

        return unique, duplicates_removed
