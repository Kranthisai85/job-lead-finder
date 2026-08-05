from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import TypeVar

from app.ai.service import AIEmailService
from app.ai.types import GeneratedEmail
from app.collectors.types import CompanyLead
from app.core.logger import get_logger
from app.email_queue.service import EmailQueueService
from app.email_queue.types import EmailQueueItem
from app.lead_generation.statistics import build_statistics, finalize_report
from app.lead_generation.types import (
    LeadGenerationReport,
    LeadGenerationResult,
    StageTiming,
)
from app.personalization.service import CompanyPersonalizationService
from app.personalization.types import PersonalizedEmailContext
from app.pipeline.persistence import PipelinePersistenceService
from app.pipeline.persistence_types import PersistenceResult
from app.pipeline.service import LeadPipelineService
from app.pipeline.types import CompleteLead, StartupSeed
from app.source_manager.service import SourceCollectionService
from app.source_manager.types import SourceCollectionReport
from app.validation.types import compute_lead_score

T = TypeVar("T")


class LeadGenerationOrchestrator:
    """End-to-end lead generation workflow using existing services."""

    def __init__(
        self,
        *,
        collection_service: SourceCollectionService | None = None,
        persistence_service: PipelinePersistenceService | None = None,
        pipeline_service: LeadPipelineService | None = None,
        personalization_service: CompanyPersonalizationService | None = None,
        ai_email_service: AIEmailService | None = None,
        email_queue_service: EmailQueueService | None = None,
    ) -> None:
        self.collection_service = collection_service or SourceCollectionService()
        self.persistence_service = persistence_service or PipelinePersistenceService()
        self.pipeline_service = pipeline_service or LeadPipelineService(
            persistence_service=self.persistence_service,
        )
        self.personalization_service = personalization_service or CompanyPersonalizationService()
        self.ai_email_service = ai_email_service or AIEmailService()
        self.email_queue_service = email_queue_service or EmailQueueService()
        self.logger = get_logger(__name__)

    async def run(
        self,
        *,
        limit: int | None = None,
        persist: bool = True,
        generate_emails: bool = True,
        enqueue_emails: bool = True,
    ) -> LeadGenerationReport:
        started = perf_counter()
        report = LeadGenerationReport()
        self.logger.info(
            ("lead_generation_started limit=%s persist=%s " "generate_emails=%s enqueue_emails=%s"),
            limit,
            persist,
            generate_emails,
            enqueue_emails,
        )

        collection_report, collect_timing = await self._run_stage(
            "collect",
            self.collection_service.collect_all(),
        )
        report.stage_timings.append(collect_timing)
        if not collect_timing.success or collection_report is None:
            report.errors.append(collect_timing.error or "Collection failed")
            report.statistics.duration_ms = round((perf_counter() - started) * 1000, 2)
            return finalize_report(report)

        seeds = self._to_startup_seeds(collection_report, limit=limit)
        report.statistics.total_collected = len(seeds)
        if not seeds:
            report.warnings.append("No startup seeds collected")
            report.statistics.duration_ms = round((perf_counter() - started) * 1000, 2)
            self.logger.info("lead_generation_finished collected=0")
            return finalize_report(report)

        for seed in seeds:
            result = await self._process_company(
                seed,
                persist=persist,
                generate_emails=generate_emails,
                enqueue_emails=enqueue_emails,
            )
            report.results.append(result)
            report.warnings.extend(result.warnings)
            report.errors.extend(result.errors)

        report.statistics.duration_ms = round((perf_counter() - started) * 1000, 2)
        report.statistics = build_statistics(
            report.results,
            total_collected=report.statistics.total_collected,
            duration_ms=report.statistics.duration_ms,
        )
        finalized = finalize_report(report)
        self.logger.info(
            (
                "lead_generation_finished collected=%d processed=%d persisted=%d "
                "qualified=%d emails=%d queued=%d failed=%d duration_ms=%.2f"
            ),
            finalized.statistics.total_collected,
            finalized.statistics.processed,
            finalized.statistics.persisted,
            finalized.statistics.qualified,
            finalized.statistics.emails_generated,
            finalized.statistics.queued,
            finalized.statistics.failed,
            finalized.statistics.duration_ms,
        )
        return finalized

    async def _process_company(
        self,
        seed: StartupSeed,
        *,
        persist: bool,
        generate_emails: bool,
        enqueue_emails: bool,
    ) -> LeadGenerationResult:
        started = perf_counter()
        result = LeadGenerationResult(company_name=seed.name, website=seed.website)
        self.logger.info(
            "lead_generation_company_started company=%s website=%s",
            seed.name,
            seed.website,
        )

        complete_lead, pipeline_timing = await self._run_stage(
            "pipeline",
            self.pipeline_service.process(seed),
        )
        result.stage_timings.append(pipeline_timing)
        if not pipeline_timing.success or complete_lead is None:
            result.success = False
            result.errors.append(pipeline_timing.error or "Pipeline failed")
            result.duration_ms = round((perf_counter() - started) * 1000, 2)
            return result

        lead = complete_lead
        result.qualified = self._is_qualified(lead)
        persistence_result: PersistenceResult | None = None

        if persist:
            persistence_result, persist_timing = await self._run_stage(
                "persist",
                self.persistence_service.persist(lead),
            )
            result.stage_timings.append(persist_timing)
            if not persist_timing.success or persistence_result is None:
                result.success = False
                result.errors.append(persist_timing.error or "Persistence failed")
            elif persistence_result.skipped:
                result.warnings.append(persistence_result.skip_reason or "Persistence skipped")
            else:
                result.persisted = bool(persistence_result.company_id)
                result.company_id = persistence_result.company_id
                if persistence_result.errors:
                    result.warnings.extend(persistence_result.errors)

        personalization, personalization_timing = await self._run_stage_sync(
            "personalization",
            lambda: self.personalization_service.generate(lead),
        )
        result.stage_timings.append(personalization_timing)
        if not personalization_timing.success:
            result.warnings.append(personalization_timing.error or "Personalization failed")

        generated_email: GeneratedEmail | None = None
        if generate_emails:
            generated_email, email_timing = await self._run_stage(
                "ai_email",
                self.ai_email_service.generate(lead),
            )
            result.stage_timings.append(email_timing)
            if email_timing.success and generated_email is not None:
                result.email_generated = True
                self.logger.info(
                    "lead_generation_email_generated company=%s source=%s",
                    seed.name,
                    generated_email.generation_source,
                )
            else:
                result.warnings.append(email_timing.error or "Email generation failed")

        if enqueue_emails and generated_email is not None:
            recipient = self._best_recipient(lead)
            company_id = result.company_id or self._fallback_company_id(seed)
            contact_id = self._fallback_contact_id(lead, recipient)
            if not recipient:
                result.warnings.append("No contact email available for queue")
            else:
                queued_item: EmailQueueItem | None
                queued_item, queue_timing = await self._run_stage(
                    "enqueue",
                    self.email_queue_service.enqueue(
                        generated_email=generated_email,
                        company_id=company_id,
                        contact_id=contact_id,
                        recipient_name=recipient["name"],
                        recipient_email=recipient["email"],
                        lead_score=self._lead_score(lead, personalization),
                    ),
                )
                result.stage_timings.append(queue_timing)
                if queue_timing.success and queued_item is not None:
                    result.queued = True
                    self.logger.info(
                        "lead_generation_email_queued company=%s queue_id=%s",
                        seed.name,
                        queued_item.id,
                    )
                else:
                    result.warnings.append(queue_timing.error or "Enqueue failed")

        if result.errors:
            result.success = False

        result.duration_ms = round((perf_counter() - started) * 1000, 2)
        self.logger.info(
            "lead_generation_company_completed company=%s success=%s duration_ms=%.2f",
            seed.name,
            result.success,
            result.duration_ms,
        )
        return result

    @staticmethod
    async def _run_stage(stage: str, awaitable: Awaitable[T]) -> tuple[T | None, StageTiming]:
        started = perf_counter()
        try:
            result = await awaitable
            timing = StageTiming(
                stage=stage,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                success=True,
            )
            return result, timing
        except Exception as exc:
            timing = StageTiming(
                stage=stage,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                success=False,
                error=str(exc),
            )
            return None, timing

    @staticmethod
    async def _run_stage_sync(stage: str, func: Callable[[], T]) -> tuple[T | None, StageTiming]:
        started = perf_counter()
        try:
            result = func()
            timing = StageTiming(
                stage=stage,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                success=True,
            )
            return result, timing
        except Exception as exc:
            timing = StageTiming(
                stage=stage,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                success=False,
                error=str(exc),
            )
            return None, timing

    @staticmethod
    def _to_startup_seeds(
        report: SourceCollectionReport,
        *,
        limit: int | None,
    ) -> list[StartupSeed]:
        seeds = [
            LeadGenerationOrchestrator._company_lead_to_seed(lead)
            for lead in report.unique_companies
        ]
        if limit is not None:
            return seeds[:limit]
        return seeds

    @staticmethod
    def _company_lead_to_seed(lead: CompanyLead) -> StartupSeed:
        return StartupSeed(
            name=lead.name,
            website=lead.website,
            description=lead.description,
            source=lead.source,
        )

    @staticmethod
    def _is_qualified(lead: CompleteLead) -> bool:
        if lead.qualification_report is not None:
            return lead.qualification_report.qualified
        if lead.lead_intelligence is not None and lead.lead_intelligence.qualification is not None:
            return lead.lead_intelligence.qualification.qualified
        return False

    @staticmethod
    def _best_recipient(lead: CompleteLead) -> dict[str, str] | None:
        if lead.lead_intelligence and lead.lead_intelligence.best_contact:
            contact = lead.lead_intelligence.best_contact
            if contact.email:
                return {
                    "name": contact.full_name or contact.first_name or "there",
                    "email": contact.email,
                }
        if lead.contacts and lead.contacts.contacts:
            ranked = sorted(lead.contacts.contacts, key=lambda item: item.confidence, reverse=True)
            for contact in ranked:
                if contact.email:
                    return {
                        "name": contact.full_name or contact.first_name or "there",
                        "email": contact.email,
                    }
        if lead.contacts and lead.contacts.emails:
            return {"name": "there", "email": lead.contacts.emails[0]}
        return None

    @staticmethod
    def _fallback_company_id(seed: StartupSeed) -> str:
        return seed.website.replace("https://", "").replace("http://", "").strip("/")

    @staticmethod
    def _fallback_contact_id(lead: CompleteLead, recipient: dict[str, str] | None) -> str:
        if recipient and recipient.get("email"):
            return recipient["email"]
        return f"{lead.startup.name.lower().replace(' ', '-')}-contact"

    @staticmethod
    def _lead_score(
        lead: CompleteLead,
        personalization: PersonalizedEmailContext | None,
    ) -> float:
        qualification_score = 0
        if lead.qualification_report is not None:
            qualification_score = lead.qualification_report.score
        elif lead.lead_intelligence is not None:
            qualification_score = lead.lead_intelligence.qualification_score

        contact_emails = len(lead.contacts.emails) if lead.contacts else 0
        technology_count = len(personalization.technology_names) if personalization else 0
        has_mobile_app = personalization.has_mobile_app if personalization else False
        is_good_lead = personalization.is_flutter_lead if personalization else False
        return compute_lead_score(
            qualification_score=qualification_score,
            contact_emails_found=contact_emails,
            technology_count=technology_count,
            mobile_app=has_mobile_app,
            is_good_lead=is_good_lead,
        )
