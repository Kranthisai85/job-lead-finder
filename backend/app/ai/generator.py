from __future__ import annotations

from time import perf_counter

from app.ai.client import OllamaClient
from app.ai.prompts import (
    DEFAULT_EMAIL_REQUIRED_FIELDS,
    SUBJECT_ONLY_REQUIRED_FIELDS,
    EmailPromptContext,
    build_email_prompt,
    build_followup_prompt,
    build_prompt_context,
    build_subject_prompt,
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
                update={"subject": f"Idea for {context.company_name}'s mobile experience"}
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
        started = perf_counter()
        try:
            ollama_response = await self.client.generate(prompt)
            parsed = parse_email_json(ollama_response.response, required_fields=required_fields)
            duration_ms = round((perf_counter() - started) * 1000, 2)
            return GeneratedEmail(
                subject=parsed.get("subject", ""),
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
            self.logger.warning(
                "ai_email_fallback company=%s error=%s",
                context.company_name,
                exc,
            )
            return self._fallback_email(
                personalized=personalized,
                prompt_length=len(prompt),
                response_time_ms=round((perf_counter() - started) * 1000, 2),
                error=str(exc),
            )

    @staticmethod
    def _fallback_email(
        *,
        personalized: PersonalizedEmailContext,
        prompt_length: int,
        response_time_ms: float,
        error: str,
    ) -> GeneratedEmail:
        body_parts = [
            personalized.mobile_app_opportunity,
            personalized.suggested_value_proposition,
            personalized.technologies_summary,
        ]
        body = "\n\n".join(part for part in body_parts if part.strip())
        return GeneratedEmail(
            subject=f"Quick idea for {personalized.company_name}",
            opening=personalized.personalized_opening,
            body=body,
            cta=personalized.cta_recommendation,
            signature="{{sender_name}}",
            generation_source="fallback",
            prompt_length=prompt_length,
            response_time_ms=response_time_ms,
            token_estimate=0,
            warnings=["Ollama unavailable; used deterministic personalization fallback"],
            errors=[error],
        )
