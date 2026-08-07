from __future__ import annotations

from time import perf_counter
from typing import Any

from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.company_intelligence.models import CompanyIntelligenceReport
from app.company_intelligence.repository import CompanyIntelligenceRepository
from app.contact_discovery.types import CompanyDecisionMaker, ContactCandidate
from app.core.logger import get_logger
from app.exceptions import DuplicateRecordError, NotFoundError, RepositoryError
from app.founder_enrichment.models import FounderProfile
from app.founder_enrichment.repository import FounderProfileRepository
from app.hiring_detection.types import HiringOpportunity
from app.opportunity_scoring.models import OpportunityScoreReport
from app.opportunity_scoring.repository import OpportunityScoreRepository
from app.pipeline.persistence_types import PersistenceResult
from app.pipeline.types import CompleteLead
from app.repositories.company_repository import CompanyRepository
from app.repositories.contact_repository import ContactRepository
from app.repositories.decision_maker_repository import DecisionMakerRepository
from app.repositories.hiring_opportunity_repository import HiringOpportunityRepository
from app.schemas.company import CreateCompanyRequest, UpdateCompanyRequest
from app.services.company_service import CompanyService
from app.utils.url import canonical_lead_website

EMAIL_PATTERN_TAG_PREFIX = "email_pattern:"
TECH_TAG_PREFIX = "tech:"


def format_exception_message(exc: BaseException) -> str:
    """Build a non-empty error string including exception type and cause chain."""
    parts: list[str] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current).strip()
        if text:
            parts.append(f"{type(current).__name__}: {text}")
        else:
            parts.append(type(current).__name__)
        next_exc = current.__cause__
        if next_exc is None:
            next_exc = current.__context__
        current = next_exc
    return " | caused by: ".join(parts) if parts else "UnknownError"


class PipelinePersistenceService:
    """Persist CompleteLead into existing Company/Contact collections."""

    def __init__(
        self,
        *,
        company_service: CompanyService | None = None,
        company_repository: CompanyRepository | None = None,
        contact_repository: ContactRepository | None = None,
        decision_maker_repository: DecisionMakerRepository | None = None,
        hiring_opportunity_repository: HiringOpportunityRepository | None = None,
        company_intelligence_repository: CompanyIntelligenceRepository | None = None,
        opportunity_score_repository: OpportunityScoreRepository | None = None,
        founder_profile_repository: FounderProfileRepository | None = None,
    ) -> None:
        self.company_repository = company_repository or CompanyRepository()
        self.company_service = company_service or CompanyService(self.company_repository)
        self.contact_repository = contact_repository or ContactRepository()
        self.decision_maker_repository = decision_maker_repository or DecisionMakerRepository()
        self.hiring_opportunity_repository = (
            hiring_opportunity_repository or HiringOpportunityRepository()
        )
        self.company_intelligence_repository = (
            company_intelligence_repository or CompanyIntelligenceRepository()
        )
        self.opportunity_score_repository = (
            opportunity_score_repository or OpportunityScoreRepository()
        )
        self.founder_profile_repository = founder_profile_repository or FounderProfileRepository()
        self.logger = get_logger(__name__)

    async def persist(self, lead: CompleteLead) -> PersistenceResult:
        started = perf_counter()
        result = PersistenceResult()

        website = canonical_lead_website(lead.startup.website)
        if not website:
            result.skipped = True
            result.skip_reason = "Missing or invalid website"
            result.duration_ms = round((perf_counter() - started) * 1000, 2)
            self.logger.warning(
                "persist_skipped company=%s reason=%s",
                lead.startup.name,
                result.skip_reason,
            )
            return result

        try:
            company_id, created, updated = await self._upsert_company(lead, website)
            result.company_id = company_id
            result.company_created = created
            result.company_updated = updated
            if not created and not updated:
                result.duplicates_skipped += 1
        except DuplicateKeyError as exc:
            self._record_failure(result, lead, stage="company", kind="duplicate_key", exc=exc)
            result.duration_ms = round((perf_counter() - started) * 1000, 2)
            return result
        except DuplicateRecordError as exc:
            self._record_failure(result, lead, stage="company", kind="duplicate_record", exc=exc)
            result.duration_ms = round((perf_counter() - started) * 1000, 2)
            return result
        except ValidationError as exc:
            self._record_failure(result, lead, stage="company", kind="validation", exc=exc)
            result.duration_ms = round((perf_counter() - started) * 1000, 2)
            return result
        except NotFoundError as exc:
            self._record_failure(result, lead, stage="company", kind="not_found", exc=exc)
            result.duration_ms = round((perf_counter() - started) * 1000, 2)
            return result
        except PyMongoError as exc:
            self._record_failure(result, lead, stage="company", kind="mongodb", exc=exc)
            result.duration_ms = round((perf_counter() - started) * 1000, 2)
            return result
        except RepositoryError as exc:
            self._record_failure(result, lead, stage="company", kind="repository", exc=exc)
            result.duration_ms = round((perf_counter() - started) * 1000, 2)
            return result
        except Exception as exc:
            self._record_failure(result, lead, stage="company", kind="service", exc=exc)
            result.duration_ms = round((perf_counter() - started) * 1000, 2)
            return result

        try:
            contact_stats = await self._upsert_contacts(lead, company_id)
            result.contacts_created = contact_stats["created"]
            result.contacts_updated = contact_stats["updated"]
            result.contacts_skipped = contact_stats["skipped"]
            result.duplicates_skipped += contact_stats["duplicates_skipped"]
        except DuplicateKeyError as exc:
            self._record_failure(result, lead, stage="contact", kind="duplicate_key", exc=exc)
        except DuplicateRecordError as exc:
            self._record_failure(result, lead, stage="contact", kind="duplicate_record", exc=exc)
        except ValidationError as exc:
            self._record_failure(result, lead, stage="contact", kind="validation", exc=exc)
        except PyMongoError as exc:
            self._record_failure(result, lead, stage="contact", kind="mongodb", exc=exc)
        except RepositoryError as exc:
            self._record_failure(result, lead, stage="contact", kind="repository", exc=exc)
        except Exception as exc:
            self._record_failure(result, lead, stage="contact", kind="service", exc=exc)

        try:
            dm_stats = await self._upsert_decision_makers(lead, company_id)
            result.decision_makers_created = dm_stats["created"]
            result.decision_makers_updated = dm_stats["updated"]
            result.decision_makers_skipped = dm_stats["skipped"]
        except DuplicateKeyError as exc:
            self._record_failure(
                result, lead, stage="decision_maker", kind="duplicate_key", exc=exc
            )
        except ValidationError as exc:
            self._record_failure(result, lead, stage="decision_maker", kind="validation", exc=exc)
        except PyMongoError as exc:
            self._record_failure(result, lead, stage="decision_maker", kind="mongodb", exc=exc)
        except RepositoryError as exc:
            self._record_failure(result, lead, stage="decision_maker", kind="repository", exc=exc)
        except Exception as exc:
            self._record_failure(result, lead, stage="decision_maker", kind="service", exc=exc)

        try:
            founder_stats = await self._upsert_founder_profiles(lead, company_id)
            result.founders_created = founder_stats["created"]
            result.founders_updated = founder_stats["updated"]
            result.founders_skipped = founder_stats["skipped"]
        except DuplicateKeyError as exc:
            self._record_failure(
                result, lead, stage="founder_profile", kind="duplicate_key", exc=exc
            )
        except ValidationError as exc:
            self._record_failure(result, lead, stage="founder_profile", kind="validation", exc=exc)
        except PyMongoError as exc:
            self._record_failure(result, lead, stage="founder_profile", kind="mongodb", exc=exc)
        except RepositoryError as exc:
            self._record_failure(result, lead, stage="founder_profile", kind="repository", exc=exc)
        except Exception as exc:
            self._record_failure(result, lead, stage="founder_profile", kind="service", exc=exc)

        try:
            hiring_stats = await self._upsert_hiring_opportunities(lead, company_id)
            result.hiring_opportunities_created = hiring_stats["created"]
            result.hiring_opportunities_updated = hiring_stats["updated"]
            result.hiring_opportunities_skipped = hiring_stats["skipped"]
        except DuplicateKeyError as exc:
            self._record_failure(
                result, lead, stage="hiring_opportunity", kind="duplicate_key", exc=exc
            )
        except ValidationError as exc:
            self._record_failure(
                result, lead, stage="hiring_opportunity", kind="validation", exc=exc
            )
        except PyMongoError as exc:
            self._record_failure(result, lead, stage="hiring_opportunity", kind="mongodb", exc=exc)
        except RepositoryError as exc:
            self._record_failure(
                result, lead, stage="hiring_opportunity", kind="repository", exc=exc
            )
        except Exception as exc:
            self._record_failure(result, lead, stage="hiring_opportunity", kind="service", exc=exc)

        try:
            result.company_intelligence_saved = await self._upsert_company_intelligence(
                lead, company_id
            )
        except DuplicateKeyError as exc:
            self._record_failure(
                result, lead, stage="company_intelligence", kind="duplicate_key", exc=exc
            )
        except ValidationError as exc:
            self._record_failure(
                result, lead, stage="company_intelligence", kind="validation", exc=exc
            )
        except PyMongoError as exc:
            self._record_failure(
                result, lead, stage="company_intelligence", kind="mongodb", exc=exc
            )
        except RepositoryError as exc:
            self._record_failure(
                result, lead, stage="company_intelligence", kind="repository", exc=exc
            )
        except Exception as exc:
            self._record_failure(
                result, lead, stage="company_intelligence", kind="service", exc=exc
            )

        try:
            result.opportunity_score_saved = await self._upsert_opportunity_score(lead, company_id)
        except DuplicateKeyError as exc:
            self._record_failure(
                result, lead, stage="opportunity_score", kind="duplicate_key", exc=exc
            )
        except ValidationError as exc:
            self._record_failure(
                result, lead, stage="opportunity_score", kind="validation", exc=exc
            )
        except PyMongoError as exc:
            self._record_failure(result, lead, stage="opportunity_score", kind="mongodb", exc=exc)
        except RepositoryError as exc:
            self._record_failure(
                result, lead, stage="opportunity_score", kind="repository", exc=exc
            )
        except Exception as exc:
            self._record_failure(result, lead, stage="opportunity_score", kind="service", exc=exc)

        try:
            result.email_pattern_saved = await self._persist_email_pattern(lead, company_id)
        except DuplicateKeyError as exc:
            self._record_failure(result, lead, stage="email_pattern", kind="duplicate_key", exc=exc)
        except ValidationError as exc:
            self._record_failure(result, lead, stage="email_pattern", kind="validation", exc=exc)
        except PyMongoError as exc:
            self._record_failure(result, lead, stage="email_pattern", kind="mongodb", exc=exc)
        except RepositoryError as exc:
            self._record_failure(result, lead, stage="email_pattern", kind="repository", exc=exc)
        except Exception as exc:
            self._record_failure(result, lead, stage="email_pattern", kind="service", exc=exc)

        result.duration_ms = round((perf_counter() - started) * 1000, 2)
        self.logger.info(
            (
                "persist_completed company=%s company_id=%s created=%s updated=%s "
                "contacts_created=%d contacts_updated=%d contacts_skipped=%d "
                "decision_makers_created=%d decision_makers_updated=%d "
                "founders_created=%d founders_updated=%d "
                "hiring_opportunities_created=%d hiring_opportunities_updated=%d "
                "company_intelligence_saved=%s opportunity_score_saved=%s "
                "email_pattern_saved=%s duplicates_skipped=%d errors=%d duration_ms=%.2f"
            ),
            lead.startup.name,
            result.company_id,
            result.company_created,
            result.company_updated,
            result.contacts_created,
            result.contacts_updated,
            result.contacts_skipped,
            result.decision_makers_created,
            result.decision_makers_updated,
            result.founders_created,
            result.founders_updated,
            result.hiring_opportunities_created,
            result.hiring_opportunities_updated,
            result.company_intelligence_saved,
            result.opportunity_score_saved,
            result.email_pattern_saved,
            result.duplicates_skipped,
            len(result.errors),
            result.duration_ms,
        )
        return result

    def _record_failure(
        self,
        result: PersistenceResult,
        lead: CompleteLead,
        *,
        stage: str,
        kind: str,
        exc: BaseException,
    ) -> None:
        detail = format_exception_message(exc)
        message = f"{stage} persistence failed ({kind}): {detail}"
        result.errors.append(message)
        self.logger.error(
            "persist_failed company=%s website=%s stage=%s kind=%s error=%s",
            lead.startup.name,
            lead.startup.website,
            stage,
            kind,
            detail,
            exc_info=True,
        )

    async def _upsert_company(self, lead: CompleteLead, website: str) -> tuple[str, bool, bool]:
        existing = await self.company_repository.find_one({"website": website})
        payload = self._company_core_payload(lead, website)
        enrichment = self._company_enrichment_payload(lead, existing_tags=None)

        if existing is None:
            try:
                created = await self.company_service.create_company(
                    CreateCompanyRequest(
                        name=payload["name"],
                        website=website,
                        description=payload["description"],
                        industry=payload["industry"],
                        source=payload["source"],
                    )
                )
                company_id = created.id
                await self.company_repository.update(company_id, enrichment)
                return company_id, True, False
            except DuplicateRecordError:
                existing = await self.company_repository.find_one({"website": website})
                if existing is None:
                    raise

        company_id = str(existing.id)
        enrichment = self._company_enrichment_payload(lead, existing_tags=list(existing.tags or []))
        update_request = UpdateCompanyRequest(
            name=payload["name"],
            description=payload["description"],
            industry=payload["industry"],
            source=payload["source"],
        )
        await self.company_service.update_company(company_id, update_request)
        await self.company_repository.update(company_id, enrichment)
        return company_id, False, True

    def _company_core_payload(self, lead: CompleteLead, website: str) -> dict[str, Any]:
        profile = lead.company_profile
        description = (
            lead.startup.description
            or (profile.short_description if profile else None)
            or (lead.website_profile.description if lead.website_profile else None)
        )
        industry = None
        if profile and profile.industry:
            industry = profile.industry
        elif profile and profile.business_category:
            industry = profile.business_category
        elif lead.lead_intelligence and lead.lead_intelligence.company.industry:
            industry = lead.lead_intelligence.company.industry

        return {
            "name": lead.startup.name.strip(),
            "website": website,
            "description": description.strip() if isinstance(description, str) else description,
            "industry": industry,
            "source": lead.startup.source,
        }

    def _company_enrichment_payload(
        self, lead: CompleteLead, *, existing_tags: list[str] | None
    ) -> dict[str, Any]:
        tags = list(existing_tags or [])
        profile = lead.company_profile
        industry = None
        if profile and profile.industry:
            industry = profile.industry
        elif profile and profile.business_category:
            industry = profile.business_category
        if industry and industry not in tags:
            tags.insert(0, industry)

        if lead.technology_report:
            for tech in lead.technology_report.technologies:
                tag = f"{TECH_TAG_PREFIX}{tech.name}"
                if tag not in tags:
                    tags.append(tag)

        has_mobile_app = None
        if lead.mobile_report is not None:
            has_mobile_app = lead.mobile_report.has_mobile_app
        elif lead.lead_intelligence is not None:
            has_mobile_app = lead.lead_intelligence.has_mobile_app

        from app.personalization.generator import PersonalizationGenerator

        is_flutter_lead = PersonalizationGenerator.has_explicit_flutter_evidence(lead)

        country = None
        if profile and profile.headquarters:
            country = profile.headquarters

        return {
            "tags": tags,
            "has_mobile_app": has_mobile_app,
            "is_flutter_lead": is_flutter_lead,
            "country": country,
        }

    async def _upsert_contacts(self, lead: CompleteLead, company_id: str) -> dict[str, int]:
        stats = {"created": 0, "updated": 0, "skipped": 0, "duplicates_skipped": 0}
        if lead.contacts is None or not lead.contacts.contacts:
            return stats

        seen_emails: set[str] = set()
        for candidate in lead.contacts.contacts:
            email = (candidate.email or "").strip().lower() or None
            if email and email in seen_emails:
                stats["duplicates_skipped"] += 1
                stats["skipped"] += 1
                continue
            if email:
                seen_emails.add(email)

            full_name = self._contact_full_name(candidate)
            if not full_name:
                stats["skipped"] += 1
                continue

            payload = {
                "company_id": company_id,
                "full_name": full_name,
                "role": candidate.role,
                "email": email,
                "linkedin_url": candidate.linkedin,
                "confidence_score": candidate.confidence,
            }

            existing = None
            if email:
                existing = await self.contact_repository.find_one({"email": email})
            if existing is None:
                existing = await self.contact_repository.find_one(
                    {"company_id": company_id, "full_name": full_name}
                )

            if existing is None:
                await self.contact_repository.create(payload)
                stats["created"] += 1
            else:
                await self.contact_repository.update(str(existing.id), payload)
                stats["updated"] += 1
                stats["duplicates_skipped"] += 1
        return stats

    async def _upsert_decision_makers(self, lead: CompleteLead, company_id: str) -> dict[str, int]:
        stats = {"created": 0, "updated": 0, "skipped": 0}
        if lead.contacts is None or not lead.contacts.decision_makers:
            return stats

        for maker in lead.contacts.decision_makers:
            payload = self._decision_maker_payload(maker, company_id)
            if not payload["name"]:
                stats["skipped"] += 1
                continue

            existing = None
            email = payload.get("email")
            if email:
                existing = await self.decision_maker_repository.find_one(
                    {"company_id": company_id, "email": email}
                )
            if existing is None and payload.get("linkedin"):
                existing = await self.decision_maker_repository.find_one(
                    {"company_id": company_id, "linkedin": payload["linkedin"]}
                )
            if existing is None and payload.get("github"):
                existing = await self.decision_maker_repository.find_one(
                    {"company_id": company_id, "github": payload["github"]}
                )
            if existing is None:
                existing = await self.decision_maker_repository.find_one(
                    {
                        "company_id": company_id,
                        "name": payload["name"],
                        "role": payload.get("role"),
                    }
                )

            if existing is None:
                await self.decision_maker_repository.create(payload)
                stats["created"] += 1
            else:
                await self.decision_maker_repository.update(str(existing.id), payload)
                stats["updated"] += 1
        return stats

    @staticmethod
    def _decision_maker_payload(maker: CompanyDecisionMaker, company_id: str) -> dict[str, Any]:
        return {
            "company_id": company_id,
            "name": maker.name.strip(),
            "role": maker.role,
            "email": (maker.email or "").strip().lower() or None,
            "linkedin": maker.linkedin,
            "github": maker.github,
            "twitter": maker.twitter,
            "confidence": maker.confidence,
            "source_page": maker.source_page,
            "contact_score": maker.contact_score,
        }

    async def _upsert_founder_profiles(self, lead: CompleteLead, company_id: str) -> dict[str, int]:
        stats = {"created": 0, "updated": 0, "skipped": 0}
        report = lead.founder_enrichment
        if report is None or report.empty or not report.founders:
            return stats

        primary_key = None
        if report.primary_founder:
            primary_key = (
                (report.primary_founder.email or "").lower(),
                (report.primary_founder.full_name or "").lower(),
            )

        for founder in report.founders:
            payload = self._founder_profile_payload(
                founder,
                company_id,
                is_primary=bool(
                    primary_key
                    and (
                        (founder.email or "").lower(),
                        (founder.full_name or "").lower(),
                    )
                    == primary_key
                ),
            )
            if not payload["full_name"] and not payload["email"]:
                stats["skipped"] += 1
                continue

            existing = None
            if payload.get("email"):
                existing = await self.founder_profile_repository.find_one(
                    {"company_id": company_id, "email": payload["email"]}
                )
            if existing is None and payload.get("linkedin"):
                existing = await self.founder_profile_repository.find_one(
                    {"company_id": company_id, "linkedin": payload["linkedin"]}
                )
            if existing is None and payload.get("full_name"):
                existing = await self.founder_profile_repository.find_one(
                    {"company_id": company_id, "full_name": payload["full_name"]}
                )

            if existing is None:
                await self.founder_profile_repository.create(payload)
                stats["created"] += 1
            else:
                await self.founder_profile_repository.update(str(existing.id), payload)
                stats["updated"] += 1
        return stats

    @staticmethod
    def _founder_profile_payload(
        founder: FounderProfile, company_id: str, *, is_primary: bool
    ) -> dict[str, Any]:
        return {
            "company_id": company_id,
            "first_name": founder.first_name,
            "last_name": founder.last_name,
            "full_name": founder.full_name,
            "role": founder.role,
            "email": (founder.email or "").strip().lower() or None,
            "bio": founder.bio,
            "github": founder.github,
            "twitter": founder.twitter,
            "linkedin": founder.linkedin,
            "personal_website": founder.personal_website,
            "location": founder.location,
            "avatar_url": founder.avatar_url,
            "confidence": founder.confidence,
            "source_page": founder.source_page,
            "discovery_source": founder.discovery_source,
            "is_primary": is_primary,
        }

    async def _upsert_hiring_opportunities(
        self, lead: CompleteLead, company_id: str
    ) -> dict[str, int]:
        stats = {"created": 0, "updated": 0, "skipped": 0}
        if lead.hiring_report is None or not lead.hiring_report.opportunities:
            return stats

        for opportunity in lead.hiring_report.opportunities:
            payload = self._hiring_opportunity_payload(opportunity, company_id)
            if not payload["title"]:
                stats["skipped"] += 1
                continue

            existing = None
            if payload.get("url"):
                existing = await self.hiring_opportunity_repository.find_one(
                    {"company_id": company_id, "url": payload["url"]}
                )
            if existing is None:
                existing = await self.hiring_opportunity_repository.find_one(
                    {"company_id": company_id, "title": payload["title"]}
                )

            if existing is None:
                await self.hiring_opportunity_repository.create(payload)
                stats["created"] += 1
            else:
                await self.hiring_opportunity_repository.update(str(existing.id), payload)
                stats["updated"] += 1
        return stats

    @staticmethod
    def _hiring_opportunity_payload(
        opportunity: HiringOpportunity, company_id: str
    ) -> dict[str, Any]:
        return {
            "company_id": company_id,
            "title": opportunity.title.strip(),
            "department": opportunity.department,
            "location": opportunity.location,
            "remote": opportunity.remote,
            "employment_type": opportunity.employment_type,
            "url": opportunity.url,
            "provider": opportunity.provider,
            "confidence": opportunity.confidence,
            "matched_keywords": list(opportunity.matched_keywords or []),
            "seniority": opportunity.seniority,
            "source_page": opportunity.source_page,
        }

    async def _upsert_company_intelligence(self, lead: CompleteLead, company_id: str) -> bool:
        report = lead.company_intelligence
        if report is None:
            return False
        payload = self._company_intelligence_payload(report, company_id)
        existing = await self.company_intelligence_repository.find_one({"company_id": company_id})
        if existing is None:
            await self.company_intelligence_repository.create(payload)
        else:
            await self.company_intelligence_repository.update(str(existing.id), payload)
        return True

    @staticmethod
    def _company_intelligence_payload(
        report: CompanyIntelligenceReport, company_id: str
    ) -> dict[str, Any]:
        return {
            "company_id": company_id,
            "url": report.url,
            "industry": report.industry,
            "subcategory": report.subcategory,
            "business_model": report.business_model,
            "target_customer": report.target_customer,
            "pricing_model": report.pricing_model,
            "company_stage": report.company_stage,
            "estimated_team_size": report.estimated_team_size,
            "estimated_maturity": report.estimated_maturity,
            "competitors": list(report.competitors or []),
            "keywords": list(report.keywords or []),
            "pain_points": list(report.pain_points or []),
            "opportunities": list(report.opportunities or []),
            "funding_status": report.funding_status,
            "confidence": report.confidence,
            "main_product": report.main_product,
            "product_category": report.product_category,
            "has_pricing_page": report.has_pricing_page,
            "is_b2b_saas": report.is_b2b_saas,
            "is_enterprise_software": report.is_enterprise_software,
            "is_developer_tools": report.is_developer_tools,
            "is_consumer_only": report.is_consumer_only,
            "has_clear_icp": report.has_clear_icp,
            "signals": list(report.signals or []),
        }

    async def _upsert_opportunity_score(self, lead: CompleteLead, company_id: str) -> bool:
        report = lead.opportunity_score
        if report is None:
            return False
        payload = self._opportunity_score_payload(report, company_id)
        existing = await self.opportunity_score_repository.find_one({"company_id": company_id})
        if existing is None:
            await self.opportunity_score_repository.create(payload)
        else:
            await self.opportunity_score_repository.update(str(existing.id), payload)
        return True

    @staticmethod
    def _opportunity_score_payload(
        report: OpportunityScoreReport, company_id: str
    ) -> dict[str, Any]:
        return {
            "company_id": company_id,
            "url": report.url,
            "overall_score": report.overall_score,
            "priority": report.priority,
            "opportunity_level": report.opportunity_level,
            "reasons": list(report.reasons or []),
            "warnings": list(report.warnings or []),
            "recommended_action": report.recommended_action,
            "confidence": report.confidence,
            "score_breakdown": dict(report.score_breakdown or {}),
        }

    @staticmethod
    def _contact_full_name(candidate: ContactCandidate) -> str | None:
        if candidate.full_name and candidate.full_name.strip():
            return candidate.full_name.strip()
        parts = [candidate.first_name or "", candidate.last_name or ""]
        joined = " ".join(part.strip() for part in parts if part and part.strip())
        if joined:
            return joined
        if candidate.email:
            local = candidate.email.split("@", 1)[0].strip()
            if local:
                return local
        return None

    async def _persist_email_pattern(self, lead: CompleteLead, company_id: str) -> bool:
        """
        EmailDraft is outreach-only (subject/body), so email patterns are stored
        as a company tag instead of creating draft documents.
        """
        report = lead.email_pattern_report
        if report is None or not report.inferred_pattern:
            return False

        pattern_value = f"{report.inferred_pattern}@{report.domain}".lower()
        tag = f"{EMAIL_PATTERN_TAG_PREFIX}{pattern_value}"

        company = await self.company_repository.find_by_id(company_id)
        if company is None:
            return False

        tags = list(company.tags or [])
        tags = [item for item in tags if not item.startswith(EMAIL_PATTERN_TAG_PREFIX)]
        tags.append(tag)
        await self.company_repository.update(company_id, {"tags": tags})
        return True
