from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from app.collectors.types import CompanyLead
from app.company_intelligence.service import CompanyIntelligenceService
from app.contact_discovery.service import ContactDiscoveryService
from app.core.logger import get_logger, setup_logging
from app.crawler.base import HttpWebsiteCrawler
from app.crawler.service import WebsiteCrawlerService
from app.crawler.types import WebsiteProfile
from app.db.mongo import close_mongo_connection, connect_to_mongo
from app.email_patterns.service import EmailPatternService
from app.founder_enrichment.service import FounderEnrichmentService
from app.hiring_detection.service import HiringDetectionService
from app.intelligence.service import LeadIntelligenceService
from app.mobile_detection.service import MobileAppDetectionService
from app.opportunity_scoring.service import OpportunityScoringService
from app.pipeline.persistence import PipelinePersistenceService
from app.pipeline.types import CompleteLead, ProcessingMetadata
from app.pipeline.types import StartupSeed as PipelineStartupSeed
from app.qualification.service import QualificationService
from app.schemas.company import CompanyResponse
from app.technology.service import TechnologyDetectionService
from app.utils.url import normalize_website
from app.validation.report import render_report
from app.validation.types import (
from app.core.timezone import now_app
    CompanyValidationResult,
    StartupSeed,
    ValidationReport,
    ValidationSummary,
    compute_lead_score,
    count_decision_makers,
)

logger = get_logger(__name__)

DEFAULT_SAMPLE_DATA = Path(__file__).resolve().parents[2] / "sample_data" / "startups.json"


class HtmlCapturingCrawler(HttpWebsiteCrawler):
    """Wraps HTTP crawler and attaches raw HTML/headers for downstream detectors."""

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


class ValidationPipeline:
    def __init__(
        self,
        *,
        crawler_service: WebsiteCrawlerService | None = None,
        technology_service: TechnologyDetectionService | None = None,
        mobile_service: MobileAppDetectionService | None = None,
        hiring_service: HiringDetectionService | None = None,
        company_intelligence_service: CompanyIntelligenceService | None = None,
        opportunity_scoring_service: OpportunityScoringService | None = None,
        founder_enrichment_service: FounderEnrichmentService | None = None,
        qualification_service: QualificationService | None = None,
        contact_service: ContactDiscoveryService | None = None,
        intelligence_service: LeadIntelligenceService | None = None,
        email_pattern_service: EmailPatternService | None = None,
        persistence_service: PipelinePersistenceService | None = None,
    ) -> None:
        self.crawler_service = crawler_service or WebsiteCrawlerService(
            crawler=HtmlCapturingCrawler()
        )
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
        self.intelligence_service = intelligence_service or LeadIntelligenceService()
        self.email_pattern_service = email_pattern_service or EmailPatternService()
        self.persistence_service = persistence_service

    async def run(self, startups: list[StartupSeed]) -> ValidationReport:
        results: list[CompanyValidationResult] = []
        for startup in startups:
            results.append(await self.process_startup(startup))
        summary = self._build_summary(results)
        return ValidationReport(results=results, summary=summary)

    @staticmethod
    def to_complete_lead(startup: StartupSeed, result: CompanyValidationResult) -> CompleteLead:
        return CompleteLead(
            startup=PipelineStartupSeed(
                name=startup.name,
                website=startup.website,
                description=startup.description,
                source=startup.source,
            ),
            website_profile=result.website_profile,
            technology_report=result.technology_report,
            mobile_report=result.mobile_detection,
            contacts=result.contact_discovery,
            founder_enrichment=result.founder_enrichment,
            hiring_report=result.hiring_report,
            company_intelligence=result.company_intelligence,
            opportunity_score=result.opportunity_score,
            qualification_report=result.qualification,
            email_pattern_report=result.email_patterns,
            lead_intelligence=result.lead_intelligence,
            processing=ProcessingMetadata(
                success=not bool(result.errors),
                errors=list(result.errors),
                total_duration_ms=0.0,
            ),
        )

    async def process_startup(self, startup: StartupSeed) -> CompanyValidationResult:
        started_at = perf_counter()
        errors: list[str] = []
        website = startup.website.strip()
        domain = normalize_website(website) or website

        result = CompanyValidationResult(name=startup.name, website=domain)

        try:
            profile = await self.crawler_service.analyze(website)
            result.website_profile = profile
            result.website_reachable = bool(profile.valid and profile.status_code)
            if not result.website_reachable:
                errors.append("Website unreachable or invalid HTML")
        except Exception as exc:
            errors.append(f"Crawler failed: {exc}")
            result.errors = errors
            return result

        try:
            technology_report = self.technology_service.detect(profile)
            result.technology_report = technology_report
            result.technologies = [tech.name for tech in technology_report.technologies]
        except Exception as exc:
            errors.append(f"Technology detection failed: {exc}")

        try:
            mobile_detection = self.mobile_service.detect(profile)
            result.mobile_detection = mobile_detection
            result.mobile_app = mobile_detection.has_mobile_app
            result.play_store = mobile_detection.android_detected or bool(profile.play_store_links)
            result.app_store = mobile_detection.ios_detected or bool(profile.app_store_links)
        except Exception as exc:
            errors.append(f"Mobile detection failed: {exc}")

        lead = CompanyLead(
            name=startup.name,
            website=domain,
            description=startup.description or profile.description,
            source=startup.source,
            tags=[],
        )

        try:
            contact_discovery = self.contact_service.discover(profile)
            result.contact_discovery = contact_discovery
            result.contact_emails_found = len(contact_discovery.emails)
            result.decision_makers = count_decision_makers(contact_discovery)
        except Exception as exc:
            errors.append(f"Contact discovery failed: {exc}")

        try:
            founder_enrichment = self.founder_enrichment_service.enrich(
                contacts=result.contact_discovery,
                website_profile=profile,
                company_intelligence=result.company_intelligence,
                decision_makers=(
                    result.contact_discovery.decision_makers if result.contact_discovery else None
                ),
            )
            result.founder_enrichment = founder_enrichment
        except Exception as exc:
            errors.append(f"Founder enrichment failed: {exc}")

        try:
            hiring_report = self.hiring_service.detect(profile)
            result.hiring_report = hiring_report
        except Exception as exc:
            errors.append(f"Hiring detection failed: {exc}")

        try:
            company_intelligence = self.company_intelligence_service.analyze(
                profile,
                technology_report=result.technology_report,
                hiring_report=result.hiring_report,
            )
            result.company_intelligence = company_intelligence
        except Exception as exc:
            errors.append(f"Company intelligence failed: {exc}")

        try:
            opportunity_score = self.opportunity_scoring_service.score(
                url=profile.final_url or profile.url,
                source=startup.source,
                website_profile=profile,
                technology_report=result.technology_report,
                mobile_report=result.mobile_detection,
                contacts=result.contact_discovery,
                hiring_report=result.hiring_report,
                company_intelligence=result.company_intelligence,
                description=startup.description or profile.description,
            )
            result.opportunity_score = opportunity_score
        except Exception as exc:
            errors.append(f"Opportunity scoring failed: {exc}")

        try:
            qualification = self.qualification_service.qualify_enriched(
                lead,
                website_profile=profile,
                technology_report=result.technology_report,
                mobile_report=result.mobile_detection,
                contacts=result.contact_discovery,
                hiring_report=result.hiring_report,
                company_intelligence=result.company_intelligence,
            )
            result.qualification = qualification
            result.qualification_pass = qualification.qualified
            result.qualification_score = qualification.score
        except Exception as exc:
            errors.append(f"Qualification failed: {exc}")

        company = CompanyResponse(
            id=str(uuid.uuid4()),
            name=startup.name,
            website=domain,
            description=startup.description or profile.description,
            industry=None,
            source=startup.source,
            created_at=now_app(),
        )

        try:
            intelligence = self.intelligence_service.build(
                company=company,
                website_profile=profile,
                technology_report=result.technology_report,
                mobile_detection=result.mobile_detection,
                contact_discovery=result.contact_discovery,
                qualification=result.qualification,
                collector_name=startup.source,
                processing_time_ms=(perf_counter() - started_at) * 1000,
            )
            result.lead_intelligence = intelligence
            result.is_good_lead = intelligence.is_good_lead
        except Exception as exc:
            errors.append(f"Lead intelligence failed: {exc}")
            intelligence = None

        if intelligence is not None:
            try:
                email_patterns = self.email_pattern_service.discover(intelligence)
                result.email_patterns = email_patterns
                if email_patterns.inferred_pattern:
                    result.email_pattern = (
                        f"{email_patterns.inferred_pattern}@{email_patterns.domain}"
                    )
                elif email_patterns.best_candidate:
                    result.email_pattern = email_patterns.best_candidate
            except Exception as exc:
                errors.append(f"Email pattern discovery failed: {exc}")

        result.lead_score = compute_lead_score(
            qualification_score=result.qualification_score,
            contact_emails_found=result.contact_emails_found,
            technology_count=len(result.technologies),
            mobile_app=result.mobile_app,
            is_good_lead=result.is_good_lead,
        )
        result.errors = errors

        if self.persistence_service is not None:
            try:
                persist_result = await self.persistence_service.persist(
                    self.to_complete_lead(startup, result)
                )
                if persist_result.errors:
                    result.errors.extend(persist_result.errors)
                logger.info(
                    ("validation_persist company=%s company_id=%s " "created=%s updated=%s"),
                    startup.name,
                    persist_result.company_id,
                    persist_result.company_created,
                    persist_result.company_updated,
                )
            except Exception as exc:
                message = f"Persistence failed: {exc}"
                result.errors.append(message)
                logger.exception(message)

        return result

    @staticmethod
    def _build_summary(results: list[CompanyValidationResult]) -> ValidationSummary:
        processed = len(results)
        reachable = sum(1 for item in results if item.website_reachable)
        qualified = sum(1 for item in results if item.qualification_pass)
        mobile_apps = sum(1 for item in results if item.mobile_app)
        emails_found = sum(item.contact_emails_found for item in results)
        technology_success = sum(1 for item in results if item.technologies)
        good_leads = sum(1 for item in results if item.is_good_lead)
        average = sum(item.lead_score for item in results) / processed if processed else 0.0
        return ValidationSummary(
            companies_processed=processed,
            reachable=reachable,
            qualified=qualified,
            mobile_apps=mobile_apps,
            emails_found=emails_found,
            technology_detection_success=technology_success,
            average_lead_score=round(average, 1),
            good_leads=good_leads,
        )


def load_startups(path: Path) -> list[StartupSeed]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Startups file must contain a JSON array")
    return [StartupSeed.model_validate(item) for item in raw]


async def run_validation(
    *,
    input_path: Path | None = None,
    output_path: Path | None = None,
    limit: int | None = None,
    persist: bool = False,
) -> str:
    setup_logging()
    path = input_path or DEFAULT_SAMPLE_DATA
    startups = load_startups(path)
    if limit is not None:
        startups = startups[:limit]

    logger.info(
        "validation_started companies=%d source=%s persist=%s",
        len(startups),
        path,
        persist,
    )

    persistence_service: PipelinePersistenceService | None = None
    if persist:
        await connect_to_mongo()
        persistence_service = PipelinePersistenceService()

    try:
        pipeline = ValidationPipeline(persistence_service=persistence_service)
        report = await pipeline.run(startups)
        rendered = render_report(report)

        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")
            logger.info("validation_report_written path=%s", output_path)

        return rendered
    finally:
        if persist:
            await close_mongo_connection()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lead Finder end-to-end validation")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_SAMPLE_DATA,
        help="Path to startups JSON file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the report",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max number of startups to process",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist successful validation leads into MongoDB",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    rendered = asyncio.run(
        run_validation(
            input_path=args.input,
            output_path=args.output,
            limit=args.limit,
            persist=args.persist,
        )
    )
    print(rendered)


if __name__ == "__main__":
    main()
