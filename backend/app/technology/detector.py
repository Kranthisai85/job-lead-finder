from app.core.config import settings
from app.technology.rules import (
    ALL_TECHNOLOGY_NAMES,
    DEFAULT_TECHNOLOGY_RULES,
    BaseTechnologyRule,
    DetectionContext,
)
from app.technology.types import Technology, TechnologyReport


class TechnologyDetectionEngine:
    def __init__(
        self,
        rules: list[BaseTechnologyRule],
        *,
        enabled_technologies: set[str],
        minimum_confidence: int,
    ) -> None:
        self.rules = rules
        self.enabled_technologies = {name.lower() for name in enabled_technologies}
        self.minimum_confidence = minimum_confidence

    def detect(self, context: DetectionContext, *, url: str) -> TechnologyReport:
        detected: list[Technology] = []

        for rule in self.rules:
            if rule.name.lower() not in self.enabled_technologies:
                continue

            match = rule.evaluate(context)
            if not match.matched:
                continue
            if match.confidence < self.minimum_confidence:
                continue

            detected.append(
                Technology(
                    name=rule.name,
                    category=rule.category,
                    confidence=match.confidence,
                    evidence=match.evidence,
                )
            )

        detected.sort(key=lambda item: item.confidence, reverse=True)
        return TechnologyReport(
            url=url,
            technologies=detected,
            detected_count=len(detected),
        )


def build_default_engine(
    *,
    enabled_technologies: set[str] | None = None,
    minimum_confidence: int | None = None,
) -> TechnologyDetectionEngine:
    enabled = enabled_technologies or _parse_enabled_technologies(
        settings.technology_enabled_technologies
    )
    return TechnologyDetectionEngine(
        rules=[rule_cls() for rule_cls in DEFAULT_TECHNOLOGY_RULES],
        enabled_technologies=enabled,
        minimum_confidence=(
            minimum_confidence
            if minimum_confidence is not None
            else settings.technology_minimum_confidence
        ),
    )


def _parse_enabled_technologies(raw_value: str) -> set[str]:
    if not raw_value.strip() or raw_value.strip() == "*":
        return {name.lower() for name in ALL_TECHNOLOGY_NAMES}
    return {name.strip().lower() for name in raw_value.split(",") if name.strip()}
