from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.core.logger import get_logger
from app.crawler.types import WebsiteProfile
from app.hiring_detection.ats import detect_ats_provider
from app.hiring_detection.config import (
    DEFAULT_HIRING_CONFIG,
    FLUTTER_KEYWORDS,
    MOBILE_KEYWORDS,
    HiringDetectionConfig,
)
from app.hiring_detection.extractors import (
    classify_job_categories,
    extract_jobs_from_html,
    match_keywords,
)
from app.hiring_detection.types import HiringDetectionReport, HiringOpportunity


class HiringDetectionService:
    def __init__(
        self,
        *,
        config: HiringDetectionConfig | None = None,
        fetch_extra_pages: bool = True,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.config = config or DEFAULT_HIRING_CONFIG
        self.fetch_extra_pages = fetch_extra_pages
        self._http_client = http_client
        self.logger = get_logger(__name__)

    def detect(self, profile: WebsiteProfile) -> HiringDetectionReport:
        source_page = profile.final_url or profile.url
        pages: list[tuple[str, str]] = []

        homepage_html = str((profile.metadata or {}).get("html", ""))
        if homepage_html:
            pages.append((source_page, homepage_html))

        if self.fetch_extra_pages:
            pages.extend(self._load_extra_pages(profile, source_page))

        opportunities: list[HiringOpportunity] = []
        pages_scanned: list[str] = []
        providers: list[str] = []

        for page_url, html in pages:
            pages_scanned.append(page_url)
            provider = detect_ats_provider(page_url, html)
            if provider:
                providers.append(provider)
            opportunities.extend(
                extract_jobs_from_html(
                    html,
                    source_page=page_url,
                    default_provider=provider,
                )
            )

        for link in self._candidate_urls(profile, source_page):
            provider = detect_ats_provider(link)
            if not provider:
                continue
            providers.append(provider)
            if any((job.url or "").rstrip("/") == link.rstrip("/") for job in opportunities):
                continue
            matched = match_keywords(link)
            opportunities.append(
                HiringOpportunity(
                    title=f"{provider} careers board",
                    url=link,
                    provider=provider,
                    confidence=0.55,
                    matched_keywords=matched,
                    source_page=source_page,
                    department="Engineering" if matched else None,
                )
            )

        opportunities = self._dedupe(opportunities)
        report = self._build_report(
            url=source_page,
            opportunities=opportunities,
            pages_scanned=pages_scanned,
            providers=providers,
            profile=profile,
            homepage_html=homepage_html,
        )

        best = report.best_job
        self.logger.info(
            "url=%s jobs_found=%d flutter_jobs=%d provider=%s best_job=%s confidence=%.2f",
            report.url,
            report.jobs_found,
            report.flutter_jobs,
            report.provider,
            best.title if best else None,
            report.confidence,
        )
        return report

    def _build_report(
        self,
        *,
        url: str,
        opportunities: list[HiringOpportunity],
        pages_scanned: list[str],
        providers: list[str],
        profile: WebsiteProfile,
        homepage_html: str,
    ) -> HiringDetectionReport:
        flutter_jobs = 0
        mobile_jobs = 0
        frontend_jobs = 0
        engineering_jobs = 0
        remote_engineering = False

        for job in opportunities:
            categories = classify_job_categories(job.matched_keywords)
            if categories["flutter"]:
                flutter_jobs += 1
            if categories["mobile"]:
                mobile_jobs += 1
            if categories["frontend"]:
                frontend_jobs += 1
            if categories["engineering"]:
                engineering_jobs += 1
                if job.remote:
                    remote_engineering = True

        has_careers_signals = bool(
            profile.career_pages
            or (profile.metadata or {}).get("jobs_pages")
            or any(
                any(token in page.lower() for token in ("career", "job", "hiring", "join"))
                for page in pages_scanned
            )
            or match_keywords(homepage_html)
        )
        has_engineering_careers = bool(
            engineering_jobs > 0 or (has_careers_signals and match_keywords(homepage_html))
        )

        provider = None
        if providers:
            provider = max(set(providers), key=providers.count)
        else:
            for job in opportunities:
                if job.provider:
                    provider = job.provider
                    break

        best = None
        if opportunities:
            best = max(
                opportunities,
                key=lambda job: (
                    len(set(job.matched_keywords) & FLUTTER_KEYWORDS),
                    len(set(job.matched_keywords) & MOBILE_KEYWORDS),
                    job.confidence,
                    len(job.matched_keywords),
                ),
            )

        confidence = 0.0
        if opportunities:
            confidence = max(job.confidence for job in opportunities)
        elif has_careers_signals:
            confidence = 0.3
        if provider:
            confidence = min(1.0, confidence + 0.1)

        return HiringDetectionReport(
            url=url,
            jobs_found=len(opportunities),
            flutter_jobs=flutter_jobs,
            mobile_jobs=mobile_jobs,
            frontend_jobs=frontend_jobs,
            engineering_jobs=engineering_jobs,
            provider=provider,
            confidence=round(confidence, 2),
            opportunities=sorted(
                opportunities,
                key=lambda job: (-job.confidence, job.title.lower()),
            ),
            pages_scanned=pages_scanned,
            best_job=best,
            has_engineering_careers_page=has_engineering_careers,
            has_remote_engineering=remote_engineering,
        )

    def _load_extra_pages(self, profile: WebsiteProfile, base_url: str) -> list[tuple[str, str]]:
        candidates = self._candidate_urls(profile, base_url)
        fetched: list[tuple[str, str]] = []
        seen: set[str] = {(base_url or "").rstrip("/").lower()}
        client = self._http_client
        owns_client = client is None
        if owns_client:
            client = httpx.Client(
                follow_redirects=True,
                timeout=self.config.timeout_s,
                headers={"User-Agent": "LeadFinderBot/1.0 (+https://lead-finder.local)"},
            )
        assert client is not None
        try:
            for url in candidates:
                key = url.rstrip("/").lower()
                if key in seen:
                    continue
                seen.add(key)
                if len(fetched) >= self.config.max_pages:
                    break
                try:
                    response = client.get(url)
                    if response.status_code >= 400:
                        continue
                    content_type = response.headers.get("content-type", "")
                    if content_type and "html" not in content_type.lower():
                        continue
                    html = response.text
                    if not html or len(html) < 40:
                        continue
                    fetched.append((str(response.url), html))
                except Exception as exc:
                    self.logger.debug("hiring_page_fetch_failed url=%s error=%s", url, exc)
        finally:
            if owns_client:
                client.close()
        return fetched

    def _candidate_urls(self, profile: WebsiteProfile, base_url: str) -> list[str]:
        parsed = urlparse(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
        urls: list[str] = []

        for path in self.config.page_paths:
            if origin:
                urls.append(urljoin(origin + "/", path.lstrip("/")))

        urls.extend(profile.career_pages)
        metadata = profile.metadata or {}
        urls.extend(self._flatten_strings(metadata.get("jobs_pages", [])))
        urls.extend(self._flatten_strings(metadata.get("about_pages", [])))
        urls.extend(self._flatten_strings(metadata.get("internal_links", [])))
        urls.extend(self._flatten_strings(metadata.get("external_links", [])))

        filtered: list[str] = []
        seen: set[str] = set()
        for url in urls:
            key = url.rstrip("/").lower()
            if key in seen:
                continue
            seen.add(key)
            lowered = url.lower()
            if detect_ats_provider(url) or any(
                token in lowered
                for token in (
                    "career",
                    "job",
                    "hiring",
                    "join-us",
                    "work-with-us",
                    "opening",
                    "/team",
                )
            ):
                filtered.append(url)
        return filtered

    @staticmethod
    def _dedupe(opportunities: list[HiringOpportunity]) -> list[HiringOpportunity]:
        merged: dict[str, HiringOpportunity] = {}
        for job in opportunities:
            key = f"{(job.url or '').lower().rstrip('/')}|{job.title.strip().lower()}"
            existing = merged.get(key)
            if existing is None or job.confidence > existing.confidence:
                merged[key] = job
        return list(merged.values())

    @staticmethod
    def _flatten_strings(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item]
