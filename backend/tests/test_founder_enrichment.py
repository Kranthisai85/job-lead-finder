from __future__ import annotations

import pytest

from app.company_intelligence.models import CompanyIntelligenceReport
from app.contact_discovery.types import (
    CompanyDecisionMaker,
    ContactCandidate,
    ContactDiscoveryReport,
)
from app.crawler.types import WebsiteProfile
from app.founder_enrichment.service import FounderEnrichmentService


def make_profile(html: str = "", *, url: str = "https://acme.example") -> WebsiteProfile:
    return WebsiteProfile(
        url=url,
        final_url=f"{url.rstrip('/')}/",
        title="Acme",
        metadata={"html": html},
        valid=True,
    )


FOUNDER_HTML = """
<html>
  <body>
    <section class="team">
      <img src="/images/jane-avatar.jpg" alt="Jane Founder headshot" class="avatar" />
      <h2>Jane Founder</h2>
      <p>Jane Founder is the Founder &amp; CEO based in San Francisco.
         She previously built developer tools and loves Flutter.</p>
      <a href="https://linkedin.com/in/jane-founder">LinkedIn</a>
      <a href="https://github.com/janef">GitHub</a>
      <a href="https://twitter.com/janef">Twitter</a>
      <a href="https://jane.dev">Personal site</a>
    </section>
  </body>
</html>
"""


def test_empty_report_when_no_founder() -> None:
    contacts = ContactDiscoveryReport(
        url="https://acme.example",
        contacts=[],
        decision_makers=[
            CompanyDecisionMaker(name="Pat Manager", role="Engineering Manager", confidence=0.5)
        ],
        decision_makers_found=1,
    )
    report = FounderEnrichmentService().enrich(contacts=contacts)
    assert report.empty is True
    assert report.founders_found == 0
    assert report.primary_founder is None
    assert report.founders == []
    assert report.confidence == 0.0


def test_enriches_founder_from_decision_maker() -> None:
    contacts = ContactDiscoveryReport(
        url="https://acme.example",
        decision_makers=[
            CompanyDecisionMaker(
                name="Jane Founder",
                role="Founder",
                email="jane@acme.example",
                linkedin="https://linkedin.com/in/jane-founder",
                github="https://github.com/janef",
                twitter="https://twitter.com/janef",
                confidence=0.9,
                contact_score=100,
                source_page="https://acme.example/team",
            )
        ],
        decision_makers_found=1,
        contacts=[
            ContactCandidate(
                full_name="Jane Founder",
                first_name="Jane",
                last_name="Founder",
                role="Founder",
                email="jane@acme.example",
                confidence=0.9,
            )
        ],
        contact_count=1,
    )
    report = FounderEnrichmentService().enrich(
        contacts=contacts,
        website_profile=make_profile(FOUNDER_HTML),
    )
    assert report.empty is False
    assert report.founders_found == 1
    founder = report.primary_founder
    assert founder is not None
    assert founder.first_name == "Jane"
    assert founder.last_name == "Founder"
    assert founder.role == "Founder"
    assert founder.email == "jane@acme.example"
    assert founder.linkedin is not None
    assert founder.github is not None
    assert founder.twitter is not None
    assert founder.bio is not None
    assert "San Francisco" in (founder.location or founder.bio or "")
    assert founder.avatar_url is not None
    assert founder.personal_website == "https://jane.dev"
    assert founder.confidence > 0.5


def test_ceo_treated_as_founder_role() -> None:
    contacts = ContactDiscoveryReport(
        url="https://acme.example",
        decision_makers=[
            CompanyDecisionMaker(
                name="Ada Lovelace",
                role="CEO",
                email="ada@acme.example",
                confidence=0.8,
            )
        ],
        decision_makers_found=1,
    )
    report = FounderEnrichmentService().enrich(contacts=contacts)
    assert report.founders_found == 1
    assert report.primary_founder is not None
    assert report.primary_founder.first_name == "Ada"
    assert report.primary_founder.last_name == "Lovelace"


def test_dedupes_decision_maker_and_contact() -> None:
    contacts = ContactDiscoveryReport(
        url="https://acme.example",
        decision_makers=[
            CompanyDecisionMaker(
                name="Jane Founder",
                role="Founder",
                email="jane@acme.example",
                confidence=0.8,
            )
        ],
        contacts=[
            ContactCandidate(
                full_name="Jane Founder",
                role="Founder",
                email="jane@acme.example",
                linkedin="https://linkedin.com/in/jane-founder",
                confidence=0.9,
            )
        ],
        decision_makers_found=1,
        contact_count=1,
    )
    report = FounderEnrichmentService().enrich(contacts=contacts)
    assert report.founders_found == 1
    assert report.primary_founder is not None
    assert report.primary_founder.linkedin is not None


def test_company_intelligence_optional_location_fallback() -> None:
    contacts = ContactDiscoveryReport(
        url="https://acme.example",
        decision_makers=[CompanyDecisionMaker(name="Sam Owner", role="Owner", confidence=0.7)],
        decision_makers_found=1,
    )
    intel = CompanyIntelligenceReport(
        url="https://acme.example",
        keywords=["london", "saas"],
        confidence=0.5,
    )
    report = FounderEnrichmentService().enrich(
        contacts=contacts,
        company_intelligence=intel,
    )
    assert report.founders_found == 1
    assert report.primary_founder is not None
    assert report.primary_founder.location == "London"


def test_direct_decision_makers_input() -> None:
    makers = [
        CompanyDecisionMaker(
            name="Chris Co",
            role="Co-Founder",
            email="chris@acme.example",
            confidence=0.85,
        )
    ]
    report = FounderEnrichmentService().enrich(
        decision_makers=makers,
        contacts=ContactDiscoveryReport(url="https://acme.example"),
    )
    assert report.founders_found == 1
    assert report.primary_founder is not None
    assert report.primary_founder.role == "Co-Founder"


def test_logging_fields(caplog: pytest.LogCaptureFixture) -> None:
    contacts = ContactDiscoveryReport(
        url="https://acme.example",
        decision_makers=[
            CompanyDecisionMaker(
                name="Jane Founder",
                role="Founder",
                email="jane@acme.example",
                confidence=0.9,
            )
        ],
        decision_makers_found=1,
    )
    with caplog.at_level("INFO"):
        FounderEnrichmentService().enrich(contacts=contacts)
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "founders_found=" in messages
    assert "confidence=" in messages
