from app.core.logger import get_logger
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
    ) -> LeadGenerationReport:
        self.logger.info("service=LeadGenerationService action=run")
        report = await self.orchestrator.run(
            limit=limit,
            persist=persist,
            generate_emails=generate_emails,
            enqueue_emails=enqueue_emails,
        )
        self.logger.info(
            (
                "service=LeadGenerationService action=completed success=%s "
                "processed=%d queued=%d duration_ms=%.2f"
            ),
            report.success,
            report.statistics.processed,
            report.statistics.queued,
            report.statistics.duration_ms,
        )
        return report
