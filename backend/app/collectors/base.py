from abc import ABC, abstractmethod
from time import perf_counter
from typing import Any

from app.collectors.types import CollectorRunResult, CompanyLead
from app.core.logger import get_logger
from app.exceptions import DuplicateRecordError
from app.qualification.service import QualificationService
from app.schemas.company import CreateCompanyRequest
from app.services.company_service import CompanyService
from app.utils.url import canonical_lead_website, website_identity


class BaseCollector(ABC):
    def __init__(
        self,
        company_service: CompanyService,
        qualification_service: QualificationService | None = None,
    ) -> None:
        self.company_service = company_service
        self.qualification_service = qualification_service or QualificationService()
        self.logger = get_logger(self.__class__.__name__)

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def collect(self) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    async def normalize(self, raw_items: list[Any]) -> list[CompanyLead]:
        raise NotImplementedError

    async def validate(self, leads: list[CompanyLead]) -> list[CompanyLead]:
        valid_leads: list[CompanyLead] = []
        seen_websites: set[str] = set()

        for lead in leads:
            name = lead.name.strip() if lead.name else ""
            website = lead.website.strip() if lead.website else ""
            if not name or not website:
                continue

            identity = website_identity(website)
            if not identity or identity in seen_websites:
                continue

            seen_websites.add(identity)
            valid_leads.append(
                lead.model_copy(update={"website": canonical_lead_website(website), "name": name})
            )

        return valid_leads

    async def save(self, leads: list[CompanyLead]) -> int:
        saved_count = 0

        for lead in leads:
            industry = lead.tags[0] if lead.tags else None
            try:
                await self.company_service.create_company(
                    CreateCompanyRequest(
                        name=lead.name,
                        website=lead.website,
                        description=lead.description,
                        industry=industry,
                        source=lead.source,
                    )
                )
                saved_count += 1
            except DuplicateRecordError:
                self.logger.info(
                    "collector=%s action=skip_duplicate website=%s",
                    self.name,
                    lead.website,
                )

        return saved_count

    async def run(self) -> CollectorRunResult:
        started_at = perf_counter()
        self.logger.info("collector=%s status=started", self.name)

        raw_items = await self.collect()
        collected_count = len(raw_items)

        normalized_leads = await self.normalize(raw_items)
        normalized_count = len(normalized_leads)

        valid_leads = await self.validate(normalized_leads)
        valid_count = len(valid_leads)

        # Qualification scoring runs after enrichment in the pipeline.
        # Collectors persist all validated seeds so unresolved PH redirects are not dropped.
        saved_count = await self.save(valid_leads)

        duration_ms = (perf_counter() - started_at) * 1000
        self.logger.info(
            (
                "collector=%s collected=%d normalized=%d valid=%d saved=%d "
                "duration_ms=%.2f status=completed"
            ),
            self.name,
            collected_count,
            normalized_count,
            valid_count,
            saved_count,
            duration_ms,
        )

        return CollectorRunResult(
            collector_name=self.name,
            collected_count=collected_count,
            normalized_count=normalized_count,
            valid_count=valid_count,
            saved_count=saved_count,
            duration_ms=duration_ms,
        )
