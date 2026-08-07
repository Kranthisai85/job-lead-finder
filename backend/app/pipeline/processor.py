from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from app.collectors.types import CompanyLead
from app.company_intelligence.service import CompanyIntelligenceService
from app.company_profile.service import CompanyProfileService
from app.contact_discovery.service import ContactDiscoveryService
from app.core.logger import get_logger
from app.crawler.base import HttpWebsiteCrawler
from app.crawler.service import WebsiteCrawlerService
from app.crawler.types import WebsiteProfile
from app.email_patterns.service import EmailPatternService
from app.founder_enrichment.service import FounderEnrichmentService
from app.hiring_detection.service import HiringDetectionService
from app.intelligence.service import LeadIntelligenceService
from app.mobile_detection.service import MobileAppDetectionService
from app.opportunity_scoring.service import OpportunityScoringService
from app.pipeline.types import (
    PIPELINE_VERSION,
    CompleteLead,
    ProcessingMetadata,
    StageTiming,
    StartupSeed,
)
from app.qualification.service import QualificationService
from app.schemas.company import CompanyResponse
from app.technology.service import TechnologyDetectionService
from app.utils.url import is_usable_company_website, normalize_website

logger = get_logger(__name__)


class HtmlCapturingCrawler(HttpWebsiteCrawler):
    """Attaches raw HTML/headers so enrichment modules can run offline on the profile."""

    async def run(self, url: str) -> WebsiteProfile:
        started_at = perf_counter()
        self.logger.info("crawler=%s status=started url=%s", self.name, url)

        download = await self.download(url)
        if download is None:
            profile = WebsiteProfile(
                url=url,
                final_url=url,
                valid=False,
                validation_errors=["HTML download failed"],
            )
            self.logger.error(
                "crawler=%s status=failed url=%s duration_ms=%.2f",
                self.name,
                url,
                (perf_counter() - started_at) * 1000,
            )
            return profile

        soup = self.parse(download.html)
        profile = self.extract(soup, download)
        profile = self.validate(profile, download)
        metadata = dict(profile.metadata)
        metadata["html"] = download.html
        metadata["headers"] = download.headers
        profile = profile.model_copy(update={"metadata": metadata})

        self.logger.info(
            "crawler=%s status=completed url=%s valid=%s duration_ms=%.2f",
            self.name,
            url,
            profile.valid,
            (perf_counter() - started_at) * 1000,
        )
        return profile


class LeadProcessor:
    """Orchestrates enrichment modules into a CompleteLead. No business logic duplication."""

    def __init__(
        self,
        *,
        crawler_service: WebsiteCrawlerService | None = None,
        company_profile_service: CompanyProfileService | None = None,
        technology_service: TechnologyDetectionService | None = None,
        mobile_service: MobileAppDetectionService | None = None,
        hiring_service: HiringDetectionService | None = None,
        company_intelligence_service: CompanyIntelligenceService | None = None,
        opportunity_scoring_service: OpportunityScoringService | None = None,
        founder_enrichment_service: FounderEnrichmentService | None = None,
        qualification_service: QualificationService | None = None,
        contact_service: ContactDiscoveryService | None = None,
        email_pattern_service: EmailPatternService | None = None,
        intelligence_service: LeadIntelligenceService | None = None,
    ) -> None:
        self.crawler_service = crawler_service or WebsiteCrawlerService(
            crawler=HtmlCapturingCrawler()
        )
        self.company_profile_service = company_profile_service or CompanyProfileService()
        self.technology_service = technology_service or TechnologyDetectionService()
        self.mobile_service = mobile_service or MobileAppDetectionService()
        self.contact_service = contact_service or ContactDiscoveryService()
        self.founder_enrichment_service = founder_enrichment_service or FounderEnrichmentService()
        self.hiring_service = hiring_service or HiringDetectionService()
        self.company_intelligence_service = (
            company_intelligence_service or CompanyIntelligenceService()
        )
        self.opportunity_scoring_service = (
            opportunity_scoring_service or OpportunityScoringService()
        )
        self.qualification_service = qualification_service or QualificationService()
        self.email_pattern_service = email_pattern_service or EmailPatternService()
        self.intelligence_service = intelligence_service or LeadIntelligenceService()

    async def process(self, startup: StartupSeed) -> CompleteLead:
        started = perf_counter()
        started_at = datetime.now(timezone.utc)
        metadata = ProcessingMetadata(started_at=started_at)
        lead = CompleteLead(startup=startup, processing=metadata)

        website = startup.website.strip()
        domain = normalize_website(website) or website
        usable_website = is_usable_company_website(website)

        if not usable_website:
            metadata.warnings.append(
                "Skipped enrichment: website is a Product Hunt redirect, platform host, "
                "CDN intermediate, or blog host"
            )
            company_lead = CompanyLead(
                name=startup.name,
                website=website,
                description=startup.description,
                source=startup.source,
                tags=[],
            )
            lead.qualification_report = self._run_sync_stage(
                lead,
                stage="qualification",
                func=lambda: self.qualification_service.qualify(company_lead),
            )
            finished_at = datetime.now(timezone.utc)
            metadata.finished_at = finished_at
            metadata.total_duration_ms = round((perf_counter() - started) * 1000, 2)
            metadata.success = len(metadata.errors) == 0
            lead.processing = metadata
            return lead

        profile = await self._run_async_stage(
            lead,
            stage="crawler",
            func=lambda: self.crawler_service.analyze(website),
        )
        lead.website_profile = profile

        if profile is not None:
            lead.company_profile = self._run_sync_stage(
                lead,
                stage="company_profile",
                func=lambda: self.company_profile_service.extract(profile),
            )
            lead.technology_report = self._run_sync_stage(
                lead,
                stage="technology",
                func=lambda: self.technology_service.detect(profile),
            )
            lead.mobile_report = self._run_sync_stage(
                lead,
                stage="mobile",
                func=lambda: self.mobile_service.detect(profile),
            )
            lead.contacts = self._run_sync_stage(
                lead,
                stage="contacts",
                func=lambda: self.contact_service.discover(profile),
            )
            lead.founder_enrichment = self._run_sync_stage(
                lead,
                stage="founder_enrichment",
                func=lambda: self.founder_enrichment_service.enrich(
                    contacts=lead.contacts,
                    website_profile=profile,
                    company_intelligence=lead.company_intelligence,
                    decision_makers=(lead.contacts.decision_makers if lead.contacts else None),
                ),
            )
            lead.hiring_report = self._run_sync_stage(
                lead,
                stage="hiring",
                func=lambda: self.hiring_service.detect(profile),
            )
            lead.company_intelligence = self._run_sync_stage(
                lead,
                stage="company_intelligence",
                func=lambda: self.company_intelligence_service.analyze(
                    profile,
                    technology_report=lead.technology_report,
                    hiring_report=lead.hiring_report,
                ),
            )
            lead.opportunity_score = self._run_sync_stage(
                lead,
                stage="opportunity_scoring",
                func=lambda: self.opportunity_scoring_service.score(
                    url=profile.final_url or profile.url,
                    source=startup.source,
                    website_profile=profile,
                    company_profile=lead.company_profile,
                    technology_report=lead.technology_report,
                    mobile_report=lead.mobile_report,
                    contacts=lead.contacts,
                    hiring_report=lead.hiring_report,
                    company_intelligence=lead.company_intelligence,
                    description=startup.description or profile.description,
                ),
            )
        else:
            metadata.warnings.append("Skipped enrichment stages dependent on WebsiteProfile")

        company_lead = CompanyLead(
            name=startup.name,
            website=domain,
            description=startup.description
            or (profile.description if profile is not None else None)
            or (lead.company_profile.short_description if lead.company_profile else None),
            source=startup.source,
            tags=[],
        )
        lead.qualification_report = self._run_sync_stage(
            lead,
            stage="qualification",
            func=lambda: self.qualification_service.qualify_enriched(
                company_lead,
                website_profile=lead.website_profile,
                technology_report=lead.technology_report,
                mobile_report=lead.mobile_report,
                contacts=lead.contacts,
                hiring_report=lead.hiring_report,
                company_intelligence=lead.company_intelligence,
            ),
        )

        company = CompanyResponse(
            id=str(uuid.uuid4()),
            name=startup.name,
            website=domain,
            description=company_lead.description,
            industry=(
                lead.company_profile.industry
                if lead.company_profile and lead.company_profile.industry
                else None
            ),
            source=startup.source,
            created_at=datetime.now(timezone.utc),
        )

        intelligence = self._run_sync_stage(
            lead,
            stage="lead_intelligence",
            func=lambda: self.intelligence_service.build(
                company=company,
                website_profile=lead.website_profile,
                technology_report=lead.technology_report,
                mobile_detection=lead.mobile_report,
                contact_discovery=lead.contacts,
                qualification=lead.qualification_report,
                collector_name=startup.source,
                processing_time_ms=(perf_counter() - started) * 1000,
                pipeline_version=PIPELINE_VERSION,
            ),
        )
        lead.lead_intelligence = intelligence

        if intelligence is not None:
            lead.email_pattern_report = self._run_sync_stage(
                lead,
                stage="email_patterns",
                func=lambda: self.email_pattern_service.discover(intelligence),
            )
        else:
            metadata.warnings.append("Skipped email patterns because LeadIntelligence is missing")

        finished_at = datetime.now(timezone.utc)
        metadata.finished_at = finished_at
        metadata.total_duration_ms = round((perf_counter() - started) * 1000, 2)
        metadata.success = len(metadata.errors) == 0
        lead.processing = metadata

        logger.info(
            "pipeline=LeadProcessor company=%s success=%s errors=%d duration_ms=%.2f",
            startup.name,
            metadata.success,
            len(metadata.errors),
            metadata.total_duration_ms,
        )
        return lead

    async def _run_async_stage(
        self,
        lead: CompleteLead,
        *,
        stage: str,
        func: Callable[[], Awaitable[Any]],
    ) -> Any:
        started = perf_counter()
        try:
            result = await func()
            self._record_timing(lead, stage=stage, started=started, success=True)
            return result
        except Exception as exc:
            self._record_failure(lead, stage=stage, started=started, exc=exc)
            return None

    def _run_sync_stage(
        self,
        lead: CompleteLead,
        *,
        stage: str,
        func: Callable[[], Any],
    ) -> Any:
        started = perf_counter()
        try:
            result = func()
            self._record_timing(lead, stage=stage, started=started, success=True)
            return result
        except Exception as exc:
            self._record_failure(lead, stage=stage, started=started, exc=exc)
            return None

    @staticmethod
    def _record_timing(
        lead: CompleteLead,
        *,
        stage: str,
        started: float,
        success: bool,
        error: str | None = None,
    ) -> None:
        lead.processing.stage_timings.append(
            StageTiming(
                stage=stage,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                success=success,
                error=error,
            )
        )

    def _record_failure(
        self,
        lead: CompleteLead,
        *,
        stage: str,
        started: float,
        exc: Exception,
    ) -> None:
        message = f"{stage} failed: {exc}"
        lead.processing.errors.append(message)
        self._record_timing(
            lead,
            stage=stage,
            started=started,
            success=False,
            error=str(exc),
        )
        logger.warning("pipeline_stage_failed stage=%s error=%s", stage, exc)
