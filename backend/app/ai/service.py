from app.ai.generator import AIEmailGenerator
from app.ai.types import GeneratedEmail
from app.core.logger import get_logger
from app.pipeline.types import CompleteLead


class AIEmailService:
    """Public entrypoint for Ollama-backed email generation."""

    def __init__(self, generator: AIEmailGenerator | None = None) -> None:
        self.generator = generator or AIEmailGenerator()
        self.logger = get_logger(__name__)

    async def generate(self, complete_lead: CompleteLead) -> GeneratedEmail:
        self.logger.info(
            "service=AIEmailService action=generate company=%s",
            complete_lead.startup.name,
        )
        email = await self.generator.generate_email(complete_lead)
        self._log_result(email)
        return email

    async def generate_followup(
        self,
        complete_lead: CompleteLead,
        *,
        previous_subject: str,
        days_since_sent: int = 3,
    ) -> GeneratedEmail:
        self.logger.info(
            "service=AIEmailService action=generate_followup company=%s",
            complete_lead.startup.name,
        )
        email = await self.generator.generate_followup(
            complete_lead,
            previous_subject=previous_subject,
            days_since_sent=days_since_sent,
        )
        self._log_result(email)
        return email

    def _log_result(self, email: GeneratedEmail) -> None:
        self.logger.info(
            (
                "service=AIEmailService completed source=%s model=%s "
                "prompt_length=%d response_time_ms=%.2f token_estimate=%d "
                "fallback=%s errors=%d"
            ),
            email.generation_source,
            email.model,
            email.prompt_length,
            email.response_time_ms,
            email.token_estimate,
            email.generation_source == "fallback",
            len(email.errors),
        )
