from app.core.logger import get_logger
from app.personalization.generator import PersonalizationGenerator
from app.personalization.types import PersonalizedEmailContext
from app.pipeline.types import CompleteLead


class CompanyPersonalizationService:
    def __init__(self, generator: PersonalizationGenerator | None = None) -> None:
        self.generator = generator or PersonalizationGenerator()
        self.logger = get_logger(__name__)

    def generate(self, lead: CompleteLead) -> PersonalizedEmailContext:
        context = self.generator.generate(lead)
        self.logger.info(
            ("company=%s is_flutter_lead=%s has_mobile_app=%s " "confidence=%.2f warnings=%d"),
            context.company_name,
            context.is_flutter_lead,
            context.has_mobile_app,
            context.confidence_score,
            len(context.warnings),
        )
        return context
