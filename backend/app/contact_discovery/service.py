from typing import Any

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
from app.contact_discovery.types import ContactCandidate, ContactDiscoveryReport
from app.contact_discovery.validators import is_valid_email, normalize_email, score_contact
from app.core.logger import get_logger
from app.crawler.types import WebsiteProfile


class ContactDiscoveryService:
    def __init__(self, engine: ContactDiscoveryEngine | None = None) -> None:
        self.engine = engine or ContactDiscoveryEngine()
        self.logger = get_logger(__name__)

    def discover(self, profile: WebsiteProfile) -> ContactDiscoveryReport:
        html = str((profile.metadata or {}).get("html", ""))
        soup = BeautifulSoup(html, "html.parser") if html else BeautifulSoup("", "html.parser")
        source_page = profile.final_url or profile.url

        text = soup.get_text(" ", strip=True)
        mailto_emails = extract_mailto_emails(soup)
        visible_emails = extract_emails_from_text(text)
        profile_emails = [
            normalize_email(email) for email in profile.emails if is_valid_email(email)
        ]
        all_emails = sorted(set(mailto_emails + visible_emails + profile_emails))

        links = self._collect_links(profile)
        social = extract_social_profiles(f"{text}\n{html}", links)

        people = extract_people_from_html(soup, source_page)
        structured = extract_json_ld_people(soup, source_page)
        email_contacts = extract_generic_email_contacts(all_emails, source_page)
        social_contacts = self._contacts_from_social(
            linkedin_profiles=social["linkedin_profiles"],
            twitter_profiles=social["twitter_profiles"],
            source_page=source_page,
        )

        report = self.engine.build_report(
            url=source_page,
            contacts=people + structured + email_contacts + social_contacts,
            emails=all_emails,
            linkedin_profiles=[
                link
                for link in social["linkedin_profiles"] + list(profile.social_links.linkedin)
                if is_person_linkedin(link) or "/in/" in link.lower()
            ],
            twitter_profiles=social["twitter_profiles"] + list(profile.social_links.twitter),
            github_profiles=social["github_profiles"] + list(profile.social_links.github),
        )

        self.logger.info(
            "url=%s contact_count=%d email_count=%d",
            report.url,
            report.contact_count,
            len(report.emails),
        )
        return report

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
    def _contacts_from_social(
        *,
        linkedin_profiles: list[str],
        twitter_profiles: list[str],
        source_page: str,
    ) -> list[ContactCandidate]:
        contacts: list[ContactCandidate] = []
        for linkedin in linkedin_profiles:
            contacts.append(
                ContactCandidate(
                    linkedin=linkedin,
                    source_page=source_page,
                    confidence=score_contact(email=None, role=None, linkedin=linkedin),
                )
            )
        for twitter in twitter_profiles:
            contacts.append(
                ContactCandidate(
                    twitter=twitter,
                    source_page=source_page,
                    confidence=0.3,
                )
            )
        return contacts

    @staticmethod
    def _flatten_strings(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item]
