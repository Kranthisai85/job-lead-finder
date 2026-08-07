from __future__ import annotations

import re

from app.personalization import prompts
from app.personalization.types import PersonalizedEmailContext
from app.pipeline.types import CompleteLead

# Explicit Flutter/Dart phrases only — not generic mobile or web-stack hints.
_FLUTTER_PHRASE_PATTERN = re.compile(
    r"\bflutter(?:\s+(?:developer|engineer|application|mobile(?:\s+app)?|app|sdk))?\b",
    re.IGNORECASE,
)
_DART_WORD_PATTERN = re.compile(r"\bdart\b", re.IGNORECASE)
_FLUTTER_TECH_NAMES = frozenset({"flutter", "dart"})


class PersonalizationGenerator:
    """Deterministic template-based personalization (no LLM)."""

    def generate(self, lead: CompleteLead) -> PersonalizedEmailContext:
        company_name = self._company_name(lead)
        technology_names = self._technology_names(lead)
        has_mobile_app = self._has_mobile_app(lead)
        is_flutter_lead = self._is_flutter_lead(lead)
        warnings = self._build_warnings(lead, technology_names, has_mobile_app)

        company_summary = self._company_summary(lead, company_name)
        personalized_opening = self._opening(lead, company_name, technology_names)
        mobile_app_opportunity = self._mobile_opportunity(lead, company_name, has_mobile_app)
        technologies_summary = self._technologies_summary(technology_names)
        qualification_summary = self._qualification_summary(lead)
        suggested_value_proposition = self._value_proposition(
            company_name, has_mobile_app, is_flutter_lead
        )
        cta_recommendation = self._cta(lead, company_name, is_flutter_lead)
        confidence_score = self._confidence_score(lead, technology_names, has_mobile_app, warnings)

        return PersonalizedEmailContext(
            company_name=company_name,
            company_summary=company_summary,
            personalized_opening=personalized_opening,
            mobile_app_opportunity=mobile_app_opportunity,
            technologies_summary=technologies_summary,
            qualification_summary=qualification_summary,
            suggested_value_proposition=suggested_value_proposition,
            cta_recommendation=cta_recommendation,
            confidence_score=confidence_score,
            warnings=warnings,
            is_flutter_lead=is_flutter_lead,
            has_mobile_app=has_mobile_app,
            technology_names=technology_names,
        )

    @staticmethod
    def _company_name(lead: CompleteLead) -> str:
        if lead.company_profile and lead.company_profile.company_name:
            return lead.company_profile.company_name
        return lead.startup.name.strip() or "your company"

    @staticmethod
    def _technology_names(lead: CompleteLead) -> list[str]:
        if lead.technology_report and lead.technology_report.technologies:
            return [tech.name for tech in lead.technology_report.technologies]
        if lead.lead_intelligence is not None:
            return list(lead.lead_intelligence.technology_names)
        return []

    @staticmethod
    def _has_mobile_app(lead: CompleteLead) -> bool:
        if lead.mobile_report is not None:
            return lead.mobile_report.has_mobile_app
        if lead.lead_intelligence is not None:
            return lead.lead_intelligence.has_mobile_app
        return False

    @classmethod
    def _is_flutter_lead(cls, lead: CompleteLead) -> bool:
        """True only when explicit Flutter/Dart evidence exists on the lead."""
        return cls.has_explicit_flutter_evidence(lead)

    @classmethod
    def has_explicit_flutter_evidence(cls, lead: CompleteLead) -> bool:
        """Conservative Flutter signal: technology, copy, hiring, or detector evidence."""
        for name in cls._technology_names(lead):
            if name.strip().lower() in _FLUTTER_TECH_NAMES:
                return True

        if lead.hiring_report is not None and lead.hiring_report.flutter_jobs > 0:
            return True

        if lead.mobile_report is not None:
            for item in lead.mobile_report.evidence or []:
                if cls._text_mentions_flutter(item):
                    return True

        if lead.hiring_report is not None:
            for opportunity in lead.hiring_report.opportunities or []:
                parts = [opportunity.title, *(opportunity.matched_keywords or [])]
                if cls._text_mentions_flutter(" ".join(part for part in parts if part)):
                    return True

        return cls._text_mentions_flutter(cls._flutter_evidence_corpus(lead))

    @classmethod
    def _flutter_evidence_corpus(cls, lead: CompleteLead) -> str:
        parts: list[str] = []
        if lead.startup.description:
            parts.append(lead.startup.description)
        profile = lead.website_profile
        if profile is not None:
            if profile.title:
                parts.append(profile.title)
            if profile.description:
                parts.append(profile.description)
            html = ""
            if profile.metadata:
                html = str(profile.metadata.get("html") or "")
            if html:
                parts.append(html)
        company = lead.company_profile
        if company is not None:
            for value in (
                company.short_description,
                company.industry,
                company.business_category,
                company.product_type,
            ):
                if value:
                    parts.append(value)
        qualification = lead.qualification_report
        if qualification is None and lead.lead_intelligence is not None:
            qualification = lead.lead_intelligence.qualification
        if qualification is not None:
            parts.extend(qualification.reasons or [])
            parts.extend(qualification.warnings or [])
        return " ".join(parts)

    @staticmethod
    def _text_mentions_flutter(text: str) -> bool:
        if not text or not text.strip():
            return False
        return bool(_FLUTTER_PHRASE_PATTERN.search(text) or _DART_WORD_PATTERN.search(text))

    def _company_summary(self, lead: CompleteLead, company_name: str) -> str:
        profile = lead.company_profile
        description = (
            (profile.short_description if profile and profile.short_description else None)
            or lead.startup.description
            or (lead.website_profile.description if lead.website_profile else None)
            or "Their product focus is still being clarified."
        )
        product_label = self._product_label(lead)
        if profile and (profile.business_category or profile.industry):
            return prompts.COMPANY_SUMMARY_FULL.format(
                company=company_name,
                category=profile.business_category or "software",
                industry=profile.industry or product_label,
                description=description,
            )
        return prompts.COMPANY_SUMMARY_BASIC.format(
            company=company_name,
            product_label=product_label,
            description=description,
        )

    def _opening(self, lead: CompleteLead, company_name: str, technology_names: list[str]) -> str:
        product_label = self._product_label(lead)
        audience = self._audience(lead)
        if technology_names:
            return prompts.OPENING_WITH_TECH.format(
                company=company_name,
                product_label=product_label,
                technologies=self._join_names(technology_names[:4]),
            )
        if lead.startup.description or lead.company_profile:
            return prompts.OPENING_WITHOUT_TECH.format(
                company=company_name,
                product_label=product_label,
                audience=audience,
            )
        return prompts.OPENING_MINIMAL.format(company=company_name)

    def _mobile_opportunity(
        self, lead: CompleteLead, company_name: str, has_mobile_app: bool
    ) -> str:
        if not has_mobile_app:
            return prompts.MOBILE_OPPORTUNITY_NONE

        stores: list[str] = []
        report = lead.mobile_report
        if report is not None:
            if report.android_detected:
                stores.append("Google Play")
            if report.ios_detected:
                stores.append("the App Store")
        store_clause = ""
        if stores:
            store_clause = f" on {self._join_names(stores)}"
        return prompts.MOBILE_OPPORTUNITY_PRESENT.format(
            company=company_name,
            store_clause=store_clause,
        )

    @staticmethod
    def _technologies_summary(technology_names: list[str]) -> str:
        if not technology_names:
            return prompts.TECH_SUMMARY_MISSING
        return prompts.TECH_SUMMARY_PRESENT.format(
            technologies=PersonalizationGenerator._join_names(technology_names)
        )

    @staticmethod
    def _qualification_summary(lead: CompleteLead) -> str:
        qualification = lead.qualification_report
        if qualification is None and lead.lead_intelligence is not None:
            qualification = lead.lead_intelligence.qualification
        if qualification is None:
            return prompts.QUALIFICATION_MISSING

        reasons = list(qualification.reasons or [])
        reasons_clause = ""
        if reasons:
            reasons_clause = f" based on {PersonalizationGenerator._join_names(reasons[:3])}"

        template = (
            prompts.QUALIFICATION_PASS if qualification.qualified else prompts.QUALIFICATION_FAIL
        )
        return template.format(score=qualification.score, reasons_clause=reasons_clause)

    @staticmethod
    def _value_proposition(company_name: str, has_mobile_app: bool, is_flutter_lead: bool) -> str:
        if is_flutter_lead:
            return prompts.VALUE_PROP_FLUTTER.format(company=company_name)
        if has_mobile_app:
            return prompts.VALUE_PROP_WITH_MOBILE.format(company=company_name)
        return prompts.VALUE_PROP_GENERIC.format(company=company_name)

    def _cta(self, lead: CompleteLead, company_name: str, is_flutter_lead: bool) -> str:
        contact_name = self._best_contact_name(lead)
        if contact_name:
            return prompts.CTA_WITH_CONTACT.format(
                contact_name=contact_name,
                company=company_name,
            )
        if is_flutter_lead:
            return prompts.CTA_FLUTTER.format(company=company_name)
        return prompts.CTA_GENERIC.format(company=company_name)

    @staticmethod
    def _best_contact_name(lead: CompleteLead) -> str | None:
        if lead.lead_intelligence and lead.lead_intelligence.best_contact:
            contact = lead.lead_intelligence.best_contact
            if contact.full_name:
                return contact.full_name
        if lead.contacts and lead.contacts.contacts:
            ranked = sorted(
                lead.contacts.contacts,
                key=lambda item: item.confidence,
                reverse=True,
            )
            if ranked[0].full_name:
                return ranked[0].full_name
        return None

    @staticmethod
    def _product_label(lead: CompleteLead) -> str:
        profile = lead.company_profile
        if profile and profile.product_type:
            return profile.product_type
        if profile and profile.business_category:
            return profile.business_category
        return "SaaS platform"

    @staticmethod
    def _audience(lead: CompleteLead) -> str:
        profile = lead.company_profile
        if profile and profile.target_audience:
            return profile.target_audience
        return "growing teams"

    @staticmethod
    def _build_warnings(
        lead: CompleteLead,
        technology_names: list[str],
        has_mobile_app: bool,
    ) -> list[str]:
        warnings: list[str] = []
        if not technology_names:
            warnings.append("Missing technology signals")
        if lead.contacts is None or (not lead.contacts.contacts and not lead.contacts.emails):
            warnings.append("Missing contacts")
        if lead.qualification_report is None and (
            lead.lead_intelligence is None or lead.lead_intelligence.qualification is None
        ):
            warnings.append("Missing qualification data")
        if lead.mobile_report is None and lead.lead_intelligence is None:
            warnings.append("Missing mobile detection data")
        if has_mobile_app:
            warnings.append("Mobile app already detected; Flutter pitch may be weaker")
        if lead.processing.errors:
            warnings.append("Pipeline reported processing errors")
        if lead.website_profile is not None and not lead.website_profile.valid:
            warnings.append("Website profile marked invalid")
        return warnings

    @staticmethod
    def _confidence_score(
        lead: CompleteLead,
        technology_names: list[str],
        has_mobile_app: bool,
        warnings: list[str],
    ) -> float:
        score = 0.35
        if lead.company_profile is not None:
            score += 0.15
        if technology_names:
            score += min(0.20, 0.05 * len(technology_names))
        if lead.qualification_report is not None or (
            lead.lead_intelligence is not None and lead.lead_intelligence.qualification is not None
        ):
            score += 0.15
        if lead.contacts and (lead.contacts.contacts or lead.contacts.emails):
            score += 0.15
        if lead.mobile_report is not None or lead.lead_intelligence is not None:
            score += 0.05
        if has_mobile_app:
            score -= 0.10
        score -= min(0.25, 0.05 * len(warnings))
        return round(max(0.0, min(1.0, score)), 2)

    @staticmethod
    def _join_names(values: list[str]) -> str:
        cleaned = [value.strip() for value in values if value and value.strip()]
        if not cleaned:
            return "their product"
        if len(cleaned) == 1:
            return cleaned[0]
        if len(cleaned) == 2:
            return f"{cleaned[0]} and {cleaned[1]}"
        return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"
