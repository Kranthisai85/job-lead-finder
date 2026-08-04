from app.core.config import settings
from app.mobile_detection.rules import DEFAULT_MOBILE_RULES, BaseMobileRule, DetectionContext
from app.mobile_detection.types import MobileAppDetectionResult


class MobileAppDetectionEngine:
    def __init__(
        self,
        rules: list[BaseMobileRule],
        *,
        enabled: bool,
        minimum_confidence: float,
    ) -> None:
        self.rules = rules
        self.enabled = enabled
        self.minimum_confidence = minimum_confidence

    def detect(self, context: DetectionContext) -> MobileAppDetectionResult:
        if not self.enabled:
            return MobileAppDetectionResult(
                has_mobile_app=False,
                confidence=0.0,
                evidence=["Mobile detection disabled"],
            )

        evidence: list[str] = []
        detected_links: list[str] = []
        android_detected = False
        ios_detected = False
        confidence_scores: list[float] = []

        for rule in self.rules:
            match = rule.evaluate(context)
            if not match.matched:
                continue
            if match.confidence < self.minimum_confidence:
                continue

            confidence_scores.append(match.confidence)
            evidence.extend(match.evidence)
            detected_links.extend(match.detected_links)
            android_detected = android_detected or match.android
            ios_detected = ios_detected or match.ios

        unique_evidence = _unique_preserve_order(evidence)
        unique_links = _unique_preserve_order(detected_links)
        unique_evidence.sort()
        unique_links.sort()

        confidence = max(confidence_scores) if confidence_scores else 0.0
        has_mobile_app = confidence >= self.minimum_confidence and (
            android_detected or ios_detected or bool(unique_evidence)
        )

        return MobileAppDetectionResult(
            has_mobile_app=has_mobile_app,
            confidence=confidence,
            android_detected=android_detected,
            ios_detected=ios_detected,
            evidence=unique_evidence,
            detected_links=unique_links,
        )


def build_default_engine(
    *,
    enabled: bool | None = None,
    minimum_confidence: float | None = None,
) -> MobileAppDetectionEngine:
    return MobileAppDetectionEngine(
        rules=[rule_cls() for rule_cls in DEFAULT_MOBILE_RULES],
        enabled=settings.mobile_detection_enabled if enabled is None else enabled,
        minimum_confidence=(
            settings.mobile_detection_minimum_confidence
            if minimum_confidence is None
            else minimum_confidence
        ),
    )


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered
