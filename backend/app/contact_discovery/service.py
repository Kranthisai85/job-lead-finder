from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.contact_discovery.detector import ContactDiscoveryEngine
from app.contact_discovery.extractors import (
    extract_emails_from_text,
    extract_generic_email_contacts,
    extract_json_ld_people,
    extract_mailto_emails,
    extract_people_from_html,
    extract_social_profiles,
    is_person_linkedin,
)
from app.contact_discovery.ranking import EXTRA_PAGE_PATHS, EXTRA_PAGE_TIMEOUT_S, MAX_EXTRA_PAGES
from app.contact_discovery.types import ContactCandidate, ContactDiscoveryReport, DiscoverySource
from app.contact_discovery.validators import is_valid_email, normalize_email, rank_contact
from app.core.logger import get_logger
from app.crawler.types import WebsiteProfile


class ContactDiscoveryService:
    def __init__(
        self,
        engine: ContactDiscoveryEngine | None = None,
        *,
        fetch_extra_pages: bool = True,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.engine = engine or ContactDiscoveryEngine()
        self.fetch_extra_pages = fetch_extra_pages
        self._http_client = http_client
        self.logger = get_logger(__name__)

    def discover(self, profile: WebsiteProfile) -> ContactDiscoveryReport:
        source_page = profile.final_url or profile.url
        pages: list[tuple[str, str, str]] = []  # (url, html, discovery_source)

        homepage_html = str((profile.metadata or {}).get("html", ""))
        if homepage_html:
            pages.append((source_page, homepage_html, DiscoverySource.HTML.value))

        if self.fetch_extra_pages:
            for url, html, source in self._load_extra_pages(profile, source_page):
                pages.append((url, html, source))

        all_emails: set[str] = set()
        all_contacts: list[ContactCandidate] = []
        linkedin_profiles: list[str] = []
        twitter_profiles: list[str] = []
        github_profiles: list[str] = []
        pages_scanned: list[str] = []

        profile_emails = [
            normalize_email(email) for email in profile.emails if is_valid_email(email)
        ]
        all_emails.update(profile_emails)

        for page_url, html, discovery_source in pages:
            pages_scanned.append(page_url)
            soup = BeautifulSoup(html, "html.parser") if html else BeautifulSoup("", "html.parser")
            text = soup.get_text(" ", strip=True)

            mailto_emails = extract_mailto_emails(soup)
            visible_emails = extract_emails_from_text(text)
            all_emails.update(mailto_emails)
            all_emails.update(visible_emails)

            links = self._collect_links(profile) + self._links_from_soup(soup, page_url)
            social = extract_social_profiles(f"{text}\n{html}", links)
            linkedin_profiles.extend(social["linkedin_profiles"])
            twitter_profiles.extend(social["twitter_profiles"])
            github_profiles.extend(social["github_profiles"])

            all_contacts.extend(
                extract_people_from_html(
                    soup,
                    page_url,
                    discovery_source=discovery_source,
                )
            )
            all_contacts.extend(extract_json_ld_people(soup, page_url))
            all_contacts.extend(
                self._contacts_from_social(
                    linkedin_profiles=social["linkedin_profiles"],
                    twitter_profiles=social["twitter_profiles"],
                    github_profiles=social["github_profiles"],
                    source_page=page_url,
                )
            )

        email_contacts = extract_generic_email_contacts(sorted(all_emails), source_page)
        all_contacts.extend(email_contacts)

        report = self.engine.build_report(
            url=source_page,
            contacts=all_contacts,
            emails=sorted(all_emails),
            linkedin_profiles=[
                link
                for link in linkedin_profiles + list(profile.social_links.linkedin)
                if is_person_linkedin(link) or "/in/" in link.lower()
            ],
            twitter_profiles=twitter_profiles + list(profile.social_links.twitter),
            github_profiles=github_profiles + list(profile.social_links.github),
            pages_scanned=pages_scanned,
        )

        self.logger.info(
            (
                "url=%s decision_makers_found=%d generic_contacts_found=%d "
                "best_contact=%s best_contact_score=%s pages_scanned=%d"
            ),
            report.url,
            report.decision_makers_found,
            report.generic_contacts_found,
            (
                report.best_contact.email or report.best_contact.display_name
                if report.best_contact
                else None
            ),
            report.best_contact_score,
            len(report.pages_scanned),
        )
        return report

    def _load_extra_pages(
        self,
        profile: WebsiteProfile,
        base_url: str,
    ) -> list[tuple[str, str, str]]:
        candidates = self._candidate_extra_urls(profile, base_url)
        fetched: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        client = self._http_client
        owns_client = client is None
        if owns_client:
            client = httpx.Client(
                follow_redirects=True,
                timeout=EXTRA_PAGE_TIMEOUT_S,
                headers={"User-Agent": "LeadFinderBot/1.0 (+https://lead-finder.local)"},
            )
        assert client is not None
        try:
            for url, source in candidates:
                normalized = url.rstrip("/")
                if normalized in seen or normalized == (base_url or "").rstrip("/"):
                    continue
                seen.add(normalized)
                if len(fetched) >= MAX_EXTRA_PAGES:
                    break
                try:
                    response = client.get(url)
                    if response.status_code >= 400:
                        continue
                    content_type = response.headers.get("content-type", "")
                    if "html" not in content_type.lower() and content_type:
                        continue
                    html = response.text
                    if not html or len(html) < 50:
                        continue
                    fetched.append((str(response.url), html, source))
                except Exception as exc:
                    self.logger.debug("contact_extra_page_failed url=%s error=%s", url, exc)
        finally:
            if owns_client:
                client.close()
        return fetched

    def _candidate_extra_urls(
        self, profile: WebsiteProfile, base_url: str
    ) -> list[tuple[str, str]]:
        parsed = urlparse(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
        urls: list[tuple[str, str]] = []

        for path in EXTRA_PAGE_PATHS:
            if not origin:
                break
            source = self._source_for_path(path)
            urls.append((urljoin(origin + "/", path.lstrip("/")), source))

        for page in profile.contact_pages:
            urls.append((page, DiscoverySource.CONTACT_PAGE.value))

        metadata = profile.metadata or {}
        for key, source in (
            ("about_pages", DiscoverySource.ABOUT_PAGE.value),
            ("team_pages", DiscoverySource.TEAM_PAGE.value),
            ("jobs_pages", DiscoverySource.CAREERS_PAGE.value),
        ):
            for page in self._flatten_strings(metadata.get(key, [])):
                urls.append((page, source))
        for page in profile.career_pages:
            urls.append((page, DiscoverySource.CAREERS_PAGE.value))

        # Prefer same-host pages and stable order.
        deduped: list[tuple[str, str]] = []
        seen: set[str] = set()
        for url, source in urls:
            key = url.rstrip("/").lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append((url, source))
        return deduped

    @staticmethod
    def _source_for_path(path: str) -> str:
        lowered = path.lower()
        if "team" in lowered:
            return DiscoverySource.TEAM_PAGE.value
        if "about" in lowered or "company" in lowered:
            return DiscoverySource.ABOUT_PAGE.value
        if "contact" in lowered:
            return DiscoverySource.CONTACT_PAGE.value
        if any(token in lowered for token in ("career", "job", "join")):
            return DiscoverySource.CAREERS_PAGE.value
        return DiscoverySource.HTML.value

    def _collect_links(self, profile: WebsiteProfile) -> list[str]:
        metadata = profile.metadata or {}
        links: list[str] = []
        links.extend(self._flatten_strings(metadata.get("external_links", [])))
        links.extend(self._flatten_strings(metadata.get("internal_links", [])))
        links.extend(profile.contact_pages)
        links.extend(profile.social_links.linkedin)
        links.extend(profile.social_links.twitter)
        links.extend(profile.social_links.github)
        return links

    @staticmethod
    def _links_from_soup(soup: BeautifulSoup, base_url: str) -> list[str]:
        links: list[str] = []
        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href", "")).strip()
            if not href or href.startswith("#"):
                continue
            links.append(urljoin(base_url, href))
        return links

    @staticmethod
    def _contacts_from_social(
        *,
        linkedin_profiles: list[str],
        twitter_profiles: list[str],
        github_profiles: list[str],
        source_page: str,
    ) -> list[ContactCandidate]:
        contacts: list[ContactCandidate] = []
        for linkedin in linkedin_profiles:
            score, priority, confidence = rank_contact(
                email=None,
                role=None,
                linkedin=linkedin,
                full_name=None,
            )
            contacts.append(
                ContactCandidate(
                    linkedin=linkedin,
                    source_page=source_page,
                    discovery_source=DiscoverySource.SOCIAL.value,
                    contact_score=score,
                    contact_priority=priority,
                    confidence=confidence,
                )
            )
        for github in github_profiles:
            score, priority, confidence = rank_contact(
                email=None,
                role=None,
                linkedin=None,
                github=github,
                full_name=None,
            )
            contacts.append(
                ContactCandidate(
                    github=github,
                    source_page=source_page,
                    discovery_source=DiscoverySource.SOCIAL.value,
                    contact_score=score,
                    contact_priority=priority,
                    confidence=confidence,
                )
            )
        for twitter in twitter_profiles:
            contacts.append(
                ContactCandidate(
                    twitter=twitter,
                    source_page=source_page,
                    discovery_source=DiscoverySource.SOCIAL.value,
                    contact_score=30,
                    contact_priority=12,
                    confidence=0.3,
                )
            )
        return contacts

    @staticmethod
    def _flatten_strings(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item]
