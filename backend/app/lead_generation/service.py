from uuid import uuid4

from app.core.daily_logging import attach_daily_run_handler, detach_daily_run_handler
from app.core.logger import get_logger, setup_logging
from app.core.timezone import app_timezone_name
from app.db.mongo import ensure_mongo_ready
from app.lead_generation.orchestrator import LeadGenerationOrchestrator
from app.lead_generation.types import LeadGenerationReport


class LeadGenerationService:
    """Public entrypoint for the production lead generation pipeline."""

    def __init__(self, orchestrator: LeadGenerationOrchestrator | None = None) -> None:
        self.orchestrator = orchestrator or LeadGenerationOrchestrator()
        self.logger = get_logger(__name__)

    async def run(
        self,
        *,
        limit: int | None = None,
        persist: bool = True,
        generate_emails: bool = True,
        enqueue_emails: bool = True,
        run_id: str | None = None,
    ) -> LeadGenerationReport:
        active_run_id = run_id or str(uuid4())
        try:
            setup_logging()
            daily_log = attach_daily_run_handler()
            if daily_log is not None:
                self.logger.info(
                    "[PIPELINE] daily_log=%s timezone=%s",
                    daily_log,
                    app_timezone_name(),
                )
        except Exception as exc:  # noqa: BLE001 — logging must not crash pipeline
            self.logger.error("daily_logging_setup_failed error=%s", exc)

        self.logger.info(
            "[PIPELINE] Starting run_id=%s service=LeadGenerationService",
            active_run_id,
        )
        try:
            if persist or enqueue_emails:
                await ensure_mongo_ready()
            report = await self.orchestrator.run(
                limit=limit,
                persist=persist,
                generate_emails=generate_emails,
                enqueue_emails=enqueue_emails,
            )
            self.logger.info(
                (
                    "[PIPELINE] Completed run_id=%s success=%s processed=%d "
                    "queued=%d duration_ms=%.2f"
                ),
                active_run_id,
                report.success,
                report.statistics.processed,
                report.statistics.queued,
                report.statistics.duration_ms,
            )
            return report
        finally:
            try:
                detach_daily_run_handler()
            except Exception as exc:  # noqa: BLE001
                self.logger.error("daily_logging_detach_failed error=%s", exc)
