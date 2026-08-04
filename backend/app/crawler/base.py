from abc import ABC, abstractmethod
from time import perf_counter
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.core.logger import get_logger
from app.crawler.extractors import (
    classify_special_pages,
    detect_technologies,
    extract_app_store_links,
    extract_canonical_url,
    extract_emails,
    extract_favicon,
    extract_language,
    extract_links,
    extract_meta_description,
    extract_open_graph_tags,
    extract_phones,
    extract_play_store_links,
    extract_social_links,
    extract_title,
    extract_twitter_tags,
)
from app.crawler.types import DownloadResult, WebsiteProfile
from app.crawler.validators import validate_download, validate_profile


class BaseCrawler(ABC):
    def __init__(self) -> None:
        self.logger = get_logger(self.__class__.__name__)

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    async def download(self, url: str) -> DownloadResult | None:
        raise NotImplementedError

    def parse(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    def extract(self, soup: BeautifulSoup, download: DownloadResult) -> WebsiteProfile:
        base_url = download.final_url or download.url
        internal_links, external_links = extract_links(soup, base_url)
        all_links = internal_links + external_links
        special_pages = classify_special_pages(internal_links)
        text = soup.get_text(" ", strip=True)

        profile = WebsiteProfile(
            url=download.url,
            final_url=download.final_url,
            title=extract_title(soup),
            description=extract_meta_description(soup),
            favicon=extract_favicon(soup, base_url),
            language=extract_language(soup),
            status_code=download.status_code,
            response_time_ms=download.response_time_ms,
            technologies=detect_technologies(soup, download.headers),
            social_links=extract_social_links(all_links),
            contact_pages=special_pages.contact_pages,
            career_pages=special_pages.career_pages + special_pages.jobs_pages,
            blog_pages=special_pages.blog_pages,
            pricing_pages=special_pages.pricing_pages,
            documentation_pages=special_pages.documentation_pages + special_pages.api_pages,
            app_store_links=extract_app_store_links(all_links),
            play_store_links=extract_play_store_links(all_links),
            emails=extract_emails(text, soup),
            phones=extract_phones(text, soup),
            metadata={
                "canonical_url": extract_canonical_url(soup, base_url),
                "open_graph": extract_open_graph_tags(soup),
                "twitter": extract_twitter_tags(soup),
                "internal_links": internal_links,
                "external_links": external_links,
                "about_pages": special_pages.about_pages,
                "jobs_pages": special_pages.jobs_pages,
                "api_pages": special_pages.api_pages,
            },
        )
        return profile

    def validate(self, profile: WebsiteProfile, download: DownloadResult | None) -> WebsiteProfile:
        errors = validate_download(download) + validate_profile(profile)
        profile.validation_errors = errors
        profile.valid = len(errors) == 0
        return profile

    async def run(self, url: str) -> WebsiteProfile:
        started_at = perf_counter()
        self.logger.info("crawler=%s status=started url=%s", self.name, url)

        download = await self.download(url)
        if download is None:
            profile = WebsiteProfile(
                url=url,
                final_url=url,
                valid=False,
                validation_errors=["HTML download failed"],
            )
            duration_ms = (perf_counter() - started_at) * 1000
            self.logger.error(
                "crawler=%s status=failed url=%s duration_ms=%.2f",
                self.name,
                url,
                duration_ms,
            )
            return profile

        soup = self.parse(download.html)
        profile = self.extract(soup, download)
        profile = self.validate(profile, download)

        duration_ms = (perf_counter() - started_at) * 1000
        self.logger.info(
            ("crawler=%s status=completed url=%s valid=%s status_code=%s " "duration_ms=%.2f"),
            self.name,
            url,
            profile.valid,
            profile.status_code,
            duration_ms,
        )
        return profile


class HttpWebsiteCrawler(BaseCrawler):
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float | None = None,
        max_redirects: int | None = None,
        max_html_size: int | None = None,
        user_agent: str | None = None,
    ) -> None:
        super().__init__()
        self._client = client
        self.timeout = timeout if timeout is not None else settings.crawler_timeout
        self.max_redirects = (
            max_redirects if max_redirects is not None else settings.crawler_max_redirects
        )
        self.max_html_size = (
            max_html_size if max_html_size is not None else settings.crawler_max_html_size
        )
        self.user_agent = user_agent or settings.crawler_user_agent

    @property
    def name(self) -> str:
        return "http_website_crawler"

    def _normalize_url(self, url: str) -> str:
        cleaned = url.strip()
        if not cleaned:
            return cleaned
        if not cleaned.startswith(("http://", "https://")):
            return f"https://{cleaned}"
        return cleaned

    async def download(self, url: str) -> DownloadResult | None:
        target = self._normalize_url(url)
        if not target or not urlparse(target).netloc:
            self.logger.error("crawler=%s invalid_url=%s", self.name, url)
            return None

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            max_redirects=self.max_redirects,
            headers={"User-Agent": self.user_agent},
        )

        started_at = perf_counter()
        try:
            response = await client.get(target)
            content = response.content
            if len(content) > self.max_html_size:
                self.logger.error(
                    "crawler=%s url=%s error=html_too_large size=%d",
                    self.name,
                    target,
                    len(content),
                )
                return None

            html = response.text
            headers = {key.lower(): value for key, value in response.headers.items()}
            return DownloadResult(
                url=target,
                final_url=str(response.url),
                status_code=response.status_code,
                html=html,
                response_time_ms=(perf_counter() - started_at) * 1000,
                headers=headers,
            )
        except Exception:
            self.logger.exception("crawler=%s download_failed url=%s", self.name, target)
            return None
        finally:
            if owns_client:
                await client.aclose()
