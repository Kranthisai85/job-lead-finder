from app.collectors.types import CompanyLead
from app.core.config import settings
from app.qualification.rules import ALL_RULE_NAMES, DEFAULT_RULES, BaseRule
from app.qualification.types import QualificationResult


class QualificationEngine:
    def __init__(
        self,
        rules: list[BaseRule],
        *,
        passing_score: int,
        enabled_rules: set[str],
        max_score: int = 100,
    ) -> None:
        self.rules = rules
        self.passing_score = passing_score
        self.enabled_rules = enabled_rules
        self.max_score = max_score

    def qualify(self, lead: CompanyLead) -> QualificationResult:
        total_points = 0
        reasons: list[str] = []
        warnings: list[str] = []
        blocking = False

        for rule in self.rules:
            if rule.name not in self.enabled_rules:
                continue

            evaluation = rule.evaluate(lead)
            total_points += evaluation.points
            reasons.extend(evaluation.reasons)
            warnings.extend(evaluation.warnings)
            if evaluation.blocking:
                blocking = True

        score = min(total_points, self.max_score)
        qualified = not blocking and score >= self.passing_score

        return QualificationResult(
            qualified=qualified,
            score=score,
            reasons=reasons,
            warnings=warnings,
        )


def build_default_engine(
    *,
    passing_score: int | None = None,
    enabled_rules: set[str] | None = None,
) -> QualificationEngine:
    parsed_enabled_rules = enabled_rules or _parse_enabled_rules(
        settings.qualification_enabled_rules
    )
    return QualificationEngine(
        rules=[rule_cls() for rule_cls in DEFAULT_RULES],
        passing_score=passing_score or settings.qualification_passing_score,
        enabled_rules=parsed_enabled_rules,
    )


def _parse_enabled_rules(raw_value: str) -> set[str]:
    if not raw_value.strip():
        return set(ALL_RULE_NAMES)
    return {rule_name.strip().lower() for rule_name in raw_value.split(",") if rule_name.strip()}
