from __future__ import annotations

from time import perf_counter
from typing import Any

from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.contact_discovery.types import ContactCandidate
from app.core.logger import get_logger
from app.exceptions import DuplicateRecordError, NotFoundError, RepositoryError
from app.pipeline.persistence_types import PersistenceResult
from app.pipeline.types import CompleteLead
from app.repositories.company_repository import CompanyRepository
from app.repositories.contact_repository import ContactRepository
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
    ) -> None:
        self.company_repository = company_repository or CompanyRepository()
        self.company_service = company_service or CompanyService(self.company_repository)
        self.contact_repository = contact_repository or ContactRepository()
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
                "email_pattern_saved=%s duplicates_skipped=%d errors=%d duration_ms=%.2f"
            ),
            lead.startup.name,
            result.company_id,
            result.company_created,
            result.company_updated,
            result.contacts_created,
            result.contacts_updated,
            result.contacts_skipped,
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

        is_flutter_lead = None
        if lead.lead_intelligence is not None:
            is_flutter_lead = lead.lead_intelligence.is_good_lead

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
