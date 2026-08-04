from typing import Any

from app.core.logger import get_logger
from app.crawler.types import WebsiteProfile
from app.technology.detector import TechnologyDetectionEngine, build_default_engine
from app.technology.rules import DetectionContext
from app.technology.types import TechnologyReport


class TechnologyDetectionService:
    def __init__(self, engine: TechnologyDetectionEngine | None = None) -> None:
        self.engine = engine or build_default_engine()
        self.logger = get_logger(__name__)

    def detect(self, profile: WebsiteProfile) -> TechnologyReport:
        context = self._build_context(profile)
        report = self.engine.detect(context, url=profile.final_url or profile.url)
        self.logger.info(
            "url=%s detected_count=%d technologies=%s",
            report.url,
            report.detected_count,
            [tech.name for tech in report.technologies],
        )
        return report

    def _build_context(self, profile: WebsiteProfile) -> DetectionContext:
        metadata = profile.metadata or {}
        html = str(metadata.get("html", ""))
        headers = self._extract_headers(metadata)
        extra_parts = [
            profile.title or "",
            profile.description or "",
            " ".join(profile.technologies),
            " ".join(self._flatten_strings(metadata.get("external_links", []))),
            " ".join(self._flatten_strings(metadata.get("internal_links", []))),
        ]
        return DetectionContext(
            html=html,
            headers=headers,
            extra_text="\n".join(part for part in extra_parts if part),
        )

    @staticmethod
    def _extract_headers(metadata: dict[str, Any]) -> dict[str, str]:
        raw_headers = metadata.get("headers", {})
        if not isinstance(raw_headers, dict):
            return {}
        return {str(key): str(value) for key, value in raw_headers.items()}

    @staticmethod
    def _flatten_strings(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item]
