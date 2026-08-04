from unittest.mock import AsyncMock

import pytest
from bs4 import BeautifulSoup

from app.crawler.base import HttpWebsiteCrawler
from app.crawler.extractors import (
    classify_special_pages,
    extract_emails,
    extract_links,
    extract_meta_description,
    extract_phones,
    extract_social_links,
    extract_title,
)
from app.crawler.service import WebsiteCrawlerService
from app.crawler.types import DownloadResult, WebsiteProfile
from app.crawler.validators import validate_download, validate_profile

SAMPLE_HTML = """
<!DOCTYPE html>
<html lang="en">
  <head>
    <title>Acme Labs</title>
    <meta name="description" content="Acme builds modern workflow tools for startups." />
    <meta property="og:title" content="Acme Labs OG" />
    <meta property="og:description" content="Open Graph description" />
    <meta name="twitter:card" content="summary" />
    <link rel="canonical" href="https://acme.example/" />
    <link rel="icon" href="/favicon.ico" />
  </head>
  <body>
    <a href="/contact">Contact</a>
    <a href="/about">About</a>
    <a href="/careers">Careers</a>
    <a href="/jobs">Jobs</a>
    <a href="/pricing">Pricing</a>
    <a href="/blog">Blog</a>
    <a href="/docs">Documentation</a>
    <a href="/api">API</a>
    <a href="https://linkedin.com/company/acme">LinkedIn</a>
    <a href="https://twitter.com/acme">Twitter</a>
    <a href="https://github.com/acme">GitHub</a>
    <a href="https://facebook.com/acme">Facebook</a>
    <a href="https://instagram.com/acme">Instagram</a>
    <a href="https://youtube.com/@acme">YouTube</a>
    <a href="https://discord.gg/acme">Discord</a>
    <a href="https://medium.com/@acme">Medium</a>
    <a href="https://apps.apple.com/app/id123">App Store</a>
    <a href="https://play.google.com/store/apps/details?id=com.acme">Play Store</a>
    <a href="mailto:hello@acme.example">Email us</a>
    <a href="tel:+1-555-0100">Call us</a>
    <p>Reach us at support@acme.example or +1 555 0199</p>
  </body>
</html>
"""


def test_extract_title() -> None:
    soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
    assert extract_title(soup) == "Acme Labs"


def test_extract_description() -> None:
    soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
    assert extract_meta_description(soup) == "Acme builds modern workflow tools for startups."


def test_extract_social_links() -> None:
    soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
    _, external = extract_links(soup, "https://acme.example")
    social = extract_social_links(external)

    assert social.linkedin == ["https://linkedin.com/company/acme"]
    assert social.twitter == ["https://twitter.com/acme"]
    assert social.github == ["https://github.com/acme"]
    assert social.facebook == ["https://facebook.com/acme"]
    assert social.instagram == ["https://instagram.com/acme"]
    assert social.youtube == ["https://youtube.com/@acme"]
    assert social.discord == ["https://discord.gg/acme"]
    assert social.medium == ["https://medium.com/@acme"]


def test_extract_emails() -> None:
    soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
    emails = extract_emails(soup.get_text(" ", strip=True), soup)
    assert "hello@acme.example" in emails
    assert "support@acme.example" in emails


def test_extract_phones() -> None:
    soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
    phones = extract_phones(soup.get_text(" ", strip=True), soup)
    assert any("555" in phone for phone in phones)


def test_extract_internal_links() -> None:
    soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
    internal, external = extract_links(soup, "https://acme.example")

    assert "https://acme.example/contact" in internal
    assert "https://acme.example/blog" in internal
    assert any("linkedin.com" in link for link in external)


def test_special_page_detection() -> None:
    soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
    internal, _ = extract_links(soup, "https://acme.example")
    classified = classify_special_pages(internal)

    assert "https://acme.example/contact" in classified.contact_pages
    assert "https://acme.example/about" in classified.about_pages
    assert "https://acme.example/careers" in classified.career_pages
    assert "https://acme.example/jobs" in classified.jobs_pages
    assert "https://acme.example/pricing" in classified.pricing_pages
    assert "https://acme.example/blog" in classified.blog_pages
    assert "https://acme.example/docs" in classified.documentation_pages
    assert "https://acme.example/api" in classified.api_pages


def test_validate_download_and_profile() -> None:
    download = DownloadResult(
        url="https://acme.example",
        final_url="https://acme.example/",
        status_code=200,
        html=SAMPLE_HTML,
        response_time_ms=12.5,
    )
    profile = WebsiteProfile(
        url="https://acme.example",
        final_url="https://acme.example/",
        title="Acme Labs",
        status_code=200,
    )

    assert validate_download(download) == []
    assert validate_profile(profile) == []
    assert validate_download(None) == ["HTML download failed"]
    assert "Title is missing" in validate_profile(
        WebsiteProfile(url="https://acme.example", final_url="https://acme.example/")
    )


@pytest.mark.asyncio
async def test_http_crawler_run_with_mocked_download() -> None:
    crawler = HttpWebsiteCrawler()
    crawler.download = AsyncMock(  # type: ignore[method-assign]
        return_value=DownloadResult(
            url="https://acme.example",
            final_url="https://acme.example/",
            status_code=200,
            html=SAMPLE_HTML,
            response_time_ms=10.0,
            headers={"server": "nginx"},
        )
    )

    profile = await crawler.run("https://acme.example")

    assert profile.valid is True
    assert profile.title == "Acme Labs"
    assert profile.description == "Acme builds modern workflow tools for startups."
    assert profile.language == "en"
    assert "https://acme.example/contact" in profile.contact_pages
    assert profile.social_links.github == ["https://github.com/acme"]
    assert "hello@acme.example" in profile.emails
    assert profile.app_store_links
    assert profile.play_store_links
    assert "nginx" in profile.technologies


@pytest.mark.asyncio
async def test_website_crawler_service_orchestration() -> None:
    crawler = HttpWebsiteCrawler()
    crawler.download = AsyncMock(  # type: ignore[method-assign]
        return_value=DownloadResult(
            url="https://acme.example",
            final_url="https://acme.example/",
            status_code=200,
            html=SAMPLE_HTML,
            response_time_ms=8.0,
        )
    )
    service = WebsiteCrawlerService(crawler=crawler)

    profile = await service.analyze("https://acme.example")

    assert profile.valid is True
    assert profile.title == "Acme Labs"


@pytest.mark.asyncio
async def test_crawler_handles_download_failure() -> None:
    crawler = HttpWebsiteCrawler()
    crawler.download = AsyncMock(return_value=None)  # type: ignore[method-assign]

    profile = await crawler.run("https://broken.example")

    assert profile.valid is False
    assert "HTML download failed" in profile.validation_errors
