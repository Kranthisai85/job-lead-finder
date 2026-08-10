from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import TypeVar

from app.ai.service import AIEmailService
from app.ai.types import GeneratedEmail
from app.collectors.types import CompanyLead
from app.contact_discovery.validators import is_outbound_safe_email
from app.core.logger import get_logger
from app.email_queue.deliverability import domain_accepts_mail, email_domain
from app.email_queue.service import EmailQueueService
from app.email_queue.types import EmailQueueItem
from app.lead_generation.statistics import build_statistics, finalize_report
from app.lead_generation.types import LeadGenerationReport, LeadGenerationResult, StageTiming
from app.lead_scoring.service import LeadScoringService
from app.personalization.service import CompanyPersonalizationService
from app.pipeline.persistence import PipelinePersistenceService, format_exception_message
from app.pipeline.persistence_types import PersistenceResult
from app.pipeline.service import LeadPipelineService
from app.pipeline.types import CompleteLead, StartupSeed
from app.source_manager.service import SourceCollectionService
from app.source_manager.types import SourceCollectionReport

T = TypeVar("T")
logger = get_logger(__name__)


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
        lead_scoring_service: LeadScoringService | None = None,
    ) -> None:
        self.collection_service = collection_service or SourceCollectionService()
        self.persistence_service = persistence_service or PipelinePersistenceService()
        self.pipeline_service = pipeline_service or LeadPipelineService(
            persistence_service=self.persistence_service,
        )
        self.personalization_service = personalization_service or CompanyPersonalizationService()
        self.ai_email_service = ai_email_service or AIEmailService()
        self.email_queue_service = email_queue_service or EmailQueueService()
        self.lead_scoring_service = lead_scoring_service or LeadScoringService()
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
            "[PIPELINE] Starting lead generation run limit=%s persist=%s "
            "generate_emails=%s enqueue_emails=%s",
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
            self.logger.error(
                "[PIPELINE] Collection failed error=%s",
                collect_timing.error or "Collection failed",
            )
            return finalize_report(report)

        seeds = self._to_startup_seeds(collection_report, limit=limit)
        report.statistics.total_collected = len(seeds)
        self.logger.info("[PIPELINE] Discovered companies count=%d", len(seeds))
        if not seeds:
            report.warnings.append("No startup seeds collected")
            report.statistics.duration_ms = round((perf_counter() - started) * 1000, 2)
            self.logger.info(
                "[PIPELINE] Completed discovered=0 qualified=0 personalized=0 "
                "emails_generated=0 emails_queued=0 errors=0"
            )
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
        personalized = sum(
            1
            for item in finalized.results
            if any(
                timing.stage == "personalization" and timing.success
                for timing in item.stage_timings
            )
        )
        self.logger.info(
            "[PIPELINE] Completed discovered=%d qualified=%d personalized=%d "
            "emails_generated=%d emails_queued=%d errors=%d duration_ms=%.2f",
            finalized.statistics.total_collected,
            finalized.statistics.qualified,
            personalized,
            finalized.statistics.emails_generated,
            finalized.statistics.queued,
            finalized.statistics.failed + len(finalized.errors),
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
            "[PIPELINE] Processing company=%s website=%s",
            seed.name,
            seed.website,
        )

        if await self.email_queue_service.is_duplicate_company(website=seed.website):
            result.warnings.append(
                "Skipped: company already in email queue "
                "(pending/skipped/approved/sent/failed)"
            )
            result.stage_timings.append(
                StageTiming(stage="duplicate_skip", duration_ms=0.0, success=True)
            )
            result.duration_ms = round((perf_counter() - started) * 1000, 2)
            self.logger.info(
                "[PIPELINE] company=%s skipped reason=duplicate_company website=%s",
                seed.name,
                seed.website,
            )
            return result

        complete_lead, pipeline_timing = await self._run_stage(
            "pipeline",
            self.pipeline_service.process(seed),
        )
        result.stage_timings.append(pipeline_timing)
        if not pipeline_timing.success or complete_lead is None:
            result.success = False
            result.errors.append(pipeline_timing.error or "Pipeline failed")
            result.duration_ms = round((perf_counter() - started) * 1000, 2)
            self.logger.error(
                "[PIPELINE] company=%s enrichment_failed error=%s",
                seed.name,
                pipeline_timing.error or "Pipeline failed",
            )
            return result

        lead = complete_lead
        outbound_score = self.lead_scoring_service.score(lead)
        lead.outbound_lead_score = outbound_score
        eligible = self.lead_scoring_service.is_eligible(outbound_score)
        result.qualified = eligible
        self.logger.info(
            "[QUALIFICATION] company=%s score=%d status=%s eligible=%s reasons=%s",
            seed.name,
            outbound_score.score,
            outbound_score.status.value,
            str(eligible).lower(),
            "; ".join(outbound_score.reasons) if outbound_score.reasons else "none",
        )

        persistence_result: PersistenceResult | None = None

        if persist:
            persistence_result, persist_timing = await self._run_stage(
                "persist",
                self.persistence_service.persist(lead),
            )
            result.stage_timings.append(persist_timing)
            if not persist_timing.success or persistence_result is None:
                result.success = False
                error_message = (persist_timing.error or "").strip()
                if not error_message:
                    error_message = "persist stage raised an exception with an empty message"
                result.errors.append(error_message)
                self.logger.error(
                    "[PIPELINE] company=%s persist_failed error=%s",
                    seed.name,
                    error_message,
                )
            elif persistence_result.skipped:
                result.warnings.append(persistence_result.skip_reason or "Persistence skipped")
            else:
                result.persisted = bool(persistence_result.company_id)
                result.company_id = persistence_result.company_id
                if persistence_result.errors:
                    if result.persisted:
                        result.warnings.extend(persistence_result.errors)
                    else:
                        result.success = False
                        result.errors.extend(persistence_result.errors)
                        persist_timing.success = False
                        persist_timing.error = "; ".join(persistence_result.errors)
                        self.logger.error(
                            "[PIPELINE] company=%s persist_failed error=%s",
                            seed.name,
                            persist_timing.error,
                        )

        personalization, personalization_timing = await self._run_stage_sync(
            "personalization",
            lambda: self.personalization_service.generate(lead),
        )
        result.stage_timings.append(personalization_timing)
        if not personalization_timing.success or personalization is None:
            result.warnings.append(personalization_timing.error or "Personalization failed")
            self.logger.error(
                "[PERSONALIZATION] company=%s failed error=%s",
                seed.name,
                personalization_timing.error or "Personalization failed",
            )
        else:
            self.logger.info(
                "[FLUTTER] company=%s evidence=%s",
                seed.name,
                str(bool(personalization.is_flutter_lead)).lower(),
            )
            self.logger.info("[PERSONALIZATION] company=%s completed", seed.name)

        generated_email: GeneratedEmail | None = None
        if generate_emails:
            self.logger.info("[AI] company=%s generation_started", seed.name)
            generated_email, email_timing = await self._run_stage(
                "ai_email",
                self.ai_email_service.generate(lead),
            )
            result.stage_timings.append(email_timing)
            if email_timing.success and generated_email is not None:
                result.email_generated = True
                self.logger.info(
                    "[AI] company=%s source=%s",
                    seed.name,
                    generated_email.generation_source,
                )
            else:
                result.warnings.append(email_timing.error or "Email generation failed")
                self.logger.error(
                    "[AI] company=%s generation_failed error=%s",
                    seed.name,
                    email_timing.error or "Email generation failed",
                )

        if enqueue_emails and generated_email is not None:
            recipient = self._best_recipient(lead)
            company_id = result.company_id or self._fallback_company_id(seed)
            contact_id = self._fallback_contact_id(lead, recipient)
            if not recipient:
                result.warnings.append("No contact email available for queue")
                self.logger.info("[QUEUE] company=%s skipped reason=no_recipient", seed.name)
            elif await self.email_queue_service.is_duplicate_recipient(
                recipient_email=recipient["email"]
            ):
                result.warnings.append(
                    f"Skipped: recipient {recipient['email']} already in email queue"
                )
                self.logger.info(
                    "[QUEUE] company=%s skipped reason=duplicate_recipient email=%s",
                    seed.name,
                    recipient["email"],
                )
            elif not await domain_accepts_mail(email_domain(recipient["email"])):
                result.warnings.append(
                    f"Skipped: no mail (MX) records for {email_domain(recipient['email'])}"
                )
                self.logger.info(
                    "[QUEUE] company=%s skipped reason=no_mx email=%s",
                    seed.name,
                    recipient["email"],
                )
            elif not eligible:
                result.warnings.append(
                    f"Lead score {outbound_score.score} below MIN_LEAD_SCORE "
                    f"{self.lead_scoring_service.min_lead_score}"
                )
                self.logger.info(
                    "[QUEUE] company=%s skipped reason=below_min_score score=%d status=%s",
                    seed.name,
                    outbound_score.score,
                    outbound_score.status.value,
                )
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
                        lead_score=float(outbound_score.score),
                    ),
                )
                result.stage_timings.append(queue_timing)
                if queue_timing.success and queued_item is not None:
                    result.queued = True
                    self.logger.info(
                        "[QUEUE] company=%s status=%s queue_id=%s",
                        seed.name,
                        queued_item.status.value,
                        queued_item.id,
                    )
                else:
                    result.warnings.append(queue_timing.error or "Enqueue failed")
                    self.logger.error(
                        "[QUEUE] company=%s enqueue_failed error=%s",
                        seed.name,
                        queue_timing.error or "Enqueue failed",
                    )

        if result.errors:
            result.success = False

        result.duration_ms = round((perf_counter() - started) * 1000, 2)
        self.logger.info(
            "[PIPELINE] company=%s completed success=%s duration_ms=%.2f",
            seed.name,
            str(result.success).lower(),
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
            error_message = format_exception_message(exc)
            logger.error(
                "lead_generation_stage_failed stage=%s error=%s",
                stage,
                error_message,
                exc_info=True,
            )
            timing = StageTiming(
                stage=stage,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                success=False,
                error=error_message,
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
            error_message = format_exception_message(exc)
            logger.error(
                "lead_generation_stage_failed stage=%s error=%s",
                stage,
                error_message,
                exc_info=True,
            )
            timing = StageTiming(
                stage=stage,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                success=False,
                error=error_message,
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
    def _best_recipient(lead: CompleteLead) -> dict[str, str] | None:
        from app.contact_discovery.validators import normalize_person_name

        def _display_name(full_name: str | None, first_name: str | None) -> str:
            return (
                normalize_person_name(full_name)
                or normalize_person_name(first_name)
                or "there"
            )

        # Prefer person / founder-style addresses. Never cold-send hello@ / info@ / support@.
        if lead.lead_intelligence and lead.lead_intelligence.best_contact:
            contact = lead.lead_intelligence.best_contact
            if contact.email and is_outbound_safe_email(contact.email):
                return {
                    "name": _display_name(contact.full_name, contact.first_name),
                    "email": contact.email,
                }
        if lead.contacts and lead.contacts.contacts:
            ranked = sorted(lead.contacts.contacts, key=lambda item: item.confidence, reverse=True)
            for contact in ranked:
                if contact.email and is_outbound_safe_email(contact.email):
                    return {
                        "name": _display_name(contact.full_name, contact.first_name),
                        "email": contact.email,
                    }
        if lead.contacts and lead.contacts.emails:
            for email in lead.contacts.emails:
                if is_outbound_safe_email(email):
                    return {"name": "there", "email": email}
        return None

    @staticmethod
    def _fallback_company_id(seed: StartupSeed) -> str:
        return seed.website.replace("https://", "").replace("http://", "").strip("/")

    @staticmethod
    def _fallback_contact_id(lead: CompleteLead, recipient: dict[str, str] | None) -> str:
        if recipient and recipient.get("email"):
            return recipient["email"]
        return f"{lead.startup.name.lower().replace(' ', '-')}-contact"
