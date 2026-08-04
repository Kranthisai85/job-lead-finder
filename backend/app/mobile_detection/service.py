from typing import Any

from app.core.logger import get_logger
from app.crawler.types import WebsiteProfile
from app.mobile_detection.detector import MobileAppDetectionEngine, build_default_engine
from app.mobile_detection.rules import DetectionContext
from app.mobile_detection.types import MobileAppDetectionResult


class MobileAppDetectionService:
    def __init__(self, engine: MobileAppDetectionEngine | None = None) -> None:
        self.engine = engine or build_default_engine()
        self.logger = get_logger(__name__)

    def detect(self, profile: WebsiteProfile) -> MobileAppDetectionResult:
        context = self._build_context(profile)
        result = self.engine.detect(context)
        self.logger.info(
            ("url=%s has_mobile_app=%s confidence=%.2f android=%s ios=%s " "evidence_count=%d"),
            profile.final_url or profile.url,
            result.has_mobile_app,
            result.confidence,
            result.android_detected,
            result.ios_detected,
            len(result.evidence),
        )
        return result

    def _build_context(self, profile: WebsiteProfile) -> DetectionContext:
        metadata = profile.metadata or {}
        html = str(metadata.get("html", ""))
        links = self._flatten_strings(metadata.get("external_links", [])) + self._flatten_strings(
            metadata.get("internal_links", [])
        )
        links.extend(profile.app_store_links)
        links.extend(profile.play_store_links)

        extra_parts = [
            profile.title or "",
            profile.description or "",
            " ".join(profile.app_store_links),
            " ".join(profile.play_store_links),
        ]
        return DetectionContext(
            html=html,
            links=links,
            app_store_links=list(profile.app_store_links),
            play_store_links=list(profile.play_store_links),
            extra_text="\n".join(part for part in extra_parts if part),
        )

    @staticmethod
    def _flatten_strings(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item]
