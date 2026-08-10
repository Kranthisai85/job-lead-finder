from __future__ import annotations

from time import perf_counter

from app.ai.client import OllamaClient
from app.ai.prompts import (
    DEFAULT_EMAIL_REQUIRED_FIELDS,
    SUBJECT_ONLY_REQUIRED_FIELDS,
    EmailPromptContext,
    build_email_prompt,
    build_fallback_subject,
    build_followup_prompt,
    build_prompt_context,
    build_subject_prompt,
    is_generic_subject,
    parse_email_json,
)
from app.ai.types import GeneratedEmail
from app.core.logger import get_logger
from app.personalization.service import CompanyPersonalizationService
from app.personalization.types import PersonalizedEmailContext
from app.pipeline.types import CompleteLead


class AIEmailGenerator:
    def __init__(
        self,
        *,
        client: OllamaClient | None = None,
        personalization_service: CompanyPersonalizationService | None = None,
    ) -> None:
        self.client = client or OllamaClient()
        self.personalization_service = personalization_service or CompanyPersonalizationService()
        self.logger = get_logger(__name__)

    async def generate_email(self, lead: CompleteLead) -> GeneratedEmail:
        personalized = self.personalization_service.generate(lead)
        context = build_prompt_context(lead, personalized)
        prompt = build_email_prompt(context)
        return await self._generate_from_prompt(
            prompt=prompt,
            lead=lead,
            personalized=personalized,
            context=context,
            required_fields=DEFAULT_EMAIL_REQUIRED_FIELDS,
        )

    async def generate_subject(self, lead: CompleteLead) -> GeneratedEmail:
        personalized = self.personalization_service.generate(lead)
        context = build_prompt_context(lead, personalized)
        prompt = build_subject_prompt(context)
        email = await self._generate_from_prompt(
            prompt=prompt,
            lead=lead,
            personalized=personalized,
            context=context,
            required_fields=SUBJECT_ONLY_REQUIRED_FIELDS,
        )
        if email.generation_source == "fallback" and not email.subject:
            email = email.model_copy(
                update={
                    "subject": build_fallback_subject(
                        company_name=context.company_name,
                        product_description=context.product_description,
                        has_mobile_app=context.has_mobile_app,
                    )
                }
            )
        return email

    async def generate_followup(
        self,
        lead: CompleteLead,
        *,
        previous_subject: str,
        days_since_sent: int = 3,
    ) -> GeneratedEmail:
        personalized = self.personalization_service.generate(lead)
        context = build_prompt_context(lead, personalized)
        prompt = build_followup_prompt(
            context,
            previous_subject=previous_subject,
            days_since_sent=days_since_sent,
        )
        return await self._generate_from_prompt(
            prompt=prompt,
            lead=lead,
            personalized=personalized,
            context=context,
            required_fields=DEFAULT_EMAIL_REQUIRED_FIELDS,
        )

    async def _generate_from_prompt(
        self,
        *,
        prompt: str,
        lead: CompleteLead,
        personalized: PersonalizedEmailContext,
        context: EmailPromptContext,
        required_fields: tuple[str, ...] = DEFAULT_EMAIL_REQUIRED_FIELDS,
    ) -> GeneratedEmail:
        del lead  # lead already folded into context/personalized
        started = perf_counter()
        last_error: Exception | None = None
        # One extra attempt after JSON/parse failures — common with local models.
        for attempt in range(2):
            try:
                ollama_response = await self.client.generate(prompt)
                parsed = parse_email_json(
                    ollama_response.response,
                    required_fields=required_fields,
                )
                duration_ms = round((perf_counter() - started) * 1000, 2)
                subject = parsed.get("subject", "")
                if is_generic_subject(subject):
                    subject = build_fallback_subject(
                        company_name=context.company_name,
                        product_description=context.product_description,
                        has_mobile_app=context.has_mobile_app,
                    )
                return GeneratedEmail(
                    subject=subject,
                    opening=parsed.get("opening", ""),
                    body=parsed.get("body", ""),
                    cta=parsed.get("cta", ""),
                    signature=parsed.get("signature", "{{sender_name}}"),
                    generation_source="ollama",
                    model=ollama_response.model or self.client.model,
                    prompt_length=len(prompt),
                    response_time_ms=duration_ms,
                    token_estimate=OllamaClient._estimate_tokens(ollama_response.response),
                )
            except Exception as exc:
                last_error = exc
                self.logger.warning(
                    "ai_email_generate_attempt_failed company=%s attempt=%d error=%s",
                    context.company_name,
                    attempt + 1,
                    exc,
                )

        self.logger.warning(
            "ai_email_fallback company=%s error=%s",
            context.company_name,
            last_error,
        )
        return self._fallback_email(
            personalized=personalized,
            context=context,
            prompt_length=len(prompt),
            response_time_ms=round((perf_counter() - started) * 1000, 2),
            error=str(last_error) if last_error else "unknown",
        )

    @staticmethod
    def _fallback_email(
        *,
        personalized: PersonalizedEmailContext,
        context: EmailPromptContext,
        prompt_length: int,
        response_time_ms: float,
        error: str,
    ) -> GeneratedEmail:
        first = context.contact_first_name.strip()
        opening = f"Hi {first}," if first else personalized.personalized_opening
        body_parts: list[str] = []
        if opening.startswith("Hi "):
            body_parts.append(personalized.personalized_opening)
        body_parts.append(personalized.mobile_app_opportunity)
        body_parts.append(personalized.suggested_value_proposition)
        body = "\n\n".join(part for part in body_parts if part and part.strip())
        return GeneratedEmail(
            subject=build_fallback_subject(
                company_name=personalized.company_name,
                product_description=context.product_description,
                has_mobile_app=context.has_mobile_app,
            ),
            opening=opening,
            body=body,
            cta=personalized.cta_recommendation,
            signature="{{sender_name}}",
            generation_source="fallback",
            prompt_length=prompt_length,
            response_time_ms=response_time_ms,
            token_estimate=0,
            warnings=["Ollama unavailable or invalid JSON; used founder-friendly fallback"],
            errors=[error],
        )
