import pytest
from bs4 import BeautifulSoup

from app.contact_discovery.extractors import extract_emails_from_text, extract_mailto_emails
from app.contact_discovery.service import ContactDiscoveryService
from app.contact_discovery.validators import (
    is_fake_contact_name,
    is_valid_email,
    normalize_email,
    normalize_person_name,
)
from app.crawler.types import WebsiteProfile


def make_profile(
    html: str = "",
    emails: list[str] | None = None,
    *,
    url: str = "https://acme.example",
    internal_links: list[str] | None = None,
) -> WebsiteProfile:
    return WebsiteProfile(
        url=url,
        final_url=f"{url.rstrip('/')}/",
        title="Acme",
        emails=emails or [],
        metadata={
            "html": html,
            "external_links": [],
            "internal_links": internal_links or [],
        },
    )


def discover(profile: WebsiteProfile, **kwargs: object) -> object:
    service = ContactDiscoveryService(fetch_extra_pages=False, **kwargs)
    return service.discover(profile)  # type: ignore[arg-type]


def test_visible_email() -> None:
    emails = extract_emails_from_text("Reach us at hello@acme.example today")
    assert "hello@acme.example" in emails


def test_mailto_email() -> None:
    soup = BeautifulSoup('<a href="mailto:founder@acme.example">Email</a>', "html.parser")
    emails = extract_mailto_emails(soup)
    assert emails == ["founder@acme.example"]


def test_obfuscated_email() -> None:
    emails = extract_emails_from_text("Contact jane [at] acme [dot] example")
    assert "jane@acme.example" in emails


def test_rejects_fake_emails() -> None:
    assert is_valid_email("test@acme.example") is False
    assert is_valid_email("example@acme.example") is False
    assert is_valid_email("value@acme.example") is False
    assert is_valid_email("noreply@acme.example") is False
    assert is_valid_email("admin@example.com") is False
    assert is_valid_email("user@localhost") is False
    assert is_valid_email("governance@runtime.we") is False
    assert is_valid_email("live@research.example.cloudflare.pay") is False
    assert is_valid_email("founder@acme.example") is True


def test_rejects_fake_contact_names() -> None:
    assert is_fake_contact_name("Privacy Policy") is True
    assert is_fake_contact_name("Pricing") is True
    assert is_fake_contact_name("Custom For") is True
    assert is_fake_contact_name("Account Wallets") is True
    assert is_fake_contact_name("Cloud Connector") is True
    assert is_fake_contact_name("Jane Founder") is False
    assert is_fake_contact_name("Beta Testers") is True
    assert is_fake_contact_name("Hi Priya") is True
    assert is_fake_contact_name("Zephyrax Project Team") is True
    assert normalize_person_name("Hi Priya") == "Priya"
    assert normalize_person_name("Ada Lovelace") == "Ada"
    assert normalize_person_name("Beta Testers") is None


def test_founder_page_extraction() -> None:
    html = """
    <section>
      <h2>Meet the team</h2>
      <p>Jane Founder is the Founder of Acme. Reach her at jane@acme.example</p>
      <a href="https://linkedin.com/in/jane-founder">LinkedIn</a>
    </section>
    """
    report = discover(make_profile(html=html))
    assert report.decision_makers_found >= 1
    founder = next(dm for dm in report.decision_makers if dm.role == "Founder")
    assert founder.email == "jane@acme.example"
    assert founder.contact_score == 100
    assert report.best_contact is not None
    assert report.best_contact.email == "jane@acme.example"
    assert report.best_contact_score == 100


def test_team_page_extraction() -> None:
    html = """
    <div class="team">
      <article>
        <h3>John Smith</h3>
        <p>CEO</p>
        <a href="mailto:john@acme.example">Email</a>
      </article>
      <article>
        <h3>Ada Lovelace</h3>
        <p>CTO</p>
        <a href="https://github.com/ada">GitHub</a>
      </article>
    </div>
    """
    report = discover(make_profile(html=html))
    roles = {dm.role for dm in report.decision_makers}
    assert "CEO" in roles
    assert "CTO" in roles
    assert report.best_contact is not None
    assert report.best_contact.role in {"CEO", "Founder", "Co-Founder"}


def test_about_page_extraction() -> None:
    html = """
    <section id="about">
      <p>Alex Rivera, Co-Founder — alex@acme.example</p>
    </section>
    """
    report = discover(make_profile(html=html))
    assert any(dm.role == "Co-Founder" for dm in report.decision_makers)


def test_contact_page_extraction() -> None:
    html = """
    <main>
      <h1>Contact</h1>
      <p>Hiring Manager: Sam Lee — hiring@acme.example</p>
      <p>Or email hello@acme.example</p>
    </main>
    """
    report = discover(make_profile(html=html))
    assert report.best_contact is not None
    assert report.best_contact.email == "hiring@acme.example"
    assert report.generic_contacts_found >= 1


def test_duplicate_emails_collapsed() -> None:
    html = """
    <p>Support email support@acme.example</p>
    <a href="mailto:support@acme.example">Mail</a>
    """
    report = discover(make_profile(html=html, emails=["support@acme.example"]))
    support_contacts = [c for c in report.contacts if c.email == "support@acme.example"]
    assert len(support_contacts) == 1
    assert report.emails.count("support@acme.example") == 1


def test_generic_footer_emails_low_priority() -> None:
    html = """
    <footer>
      <a href="mailto:support@acme.example">Support</a>
      <a href="mailto:info@acme.example">Info</a>
      <p>Privacy Policy</p>
      <p>Terms</p>
    </footer>
    """
    report = discover(make_profile(html=html))
    assert report.decision_makers_found == 0
    assert report.generic_contacts_found >= 1
    assert report.best_contact is not None
    assert report.best_contact.contact_score <= 25
    assert not any(is_fake_contact_name(c.full_name) for c in report.contacts if c.full_name)


def test_github_repository_pages_ignored_as_contacts() -> None:
    html = """
    <a href="https://github.com/acme/cool-app">Source</a>
    <a href="https://github.com/features">Features</a>
    <footer>Pricing Documentation Marketplace Sign In</footer>
    """
    report = discover(make_profile(html=html))
    assert all("/cool-app" not in (c.github or "") for c in report.contacts)
    assert "https://github.com/acme/cool-app" not in report.github_profiles
    assert not any(c.full_name == "Pricing" for c in report.contacts)


def test_missing_emails_still_returns_named_decision_makers() -> None:
    html = """
    <div>
      <p>John Smith, CEO</p>
      <a href="https://linkedin.com/in/john-smith">LinkedIn</a>
    </div>
    """
    report = discover(make_profile(html=html))
    assert any(
        contact.role == "CEO" and contact.full_name == "John Smith" for contact in report.contacts
    )
    assert report.decision_makers_found >= 1
    assert report.best_contact is not None
    assert report.best_contact.email is None


def test_support_email_score() -> None:
    report = discover(make_profile(html="<p>Email support@acme.example</p>"))
    support = next(c for c in report.contacts if c.email == "support@acme.example")
    assert support.contact_score == 20
    assert support.confidence == pytest.approx(0.2)


def test_confidence_ordering_prefers_founder() -> None:
    html = """
    <section>
      <p>Jane Founder, Founder - jane@acme.example</p>
      <p>Reach support@acme.example for help</p>
      <p>General contact@acme.example</p>
    </section>
    """
    report = discover(make_profile(html=html))
    assert report.contacts[0].email == "jane@acme.example"
    assert report.best_contact_score == 100


def test_linkedin_extraction() -> None:
    html = '<a href="https://linkedin.com/in/ada-lovelace">Ada</a>'
    report = discover(make_profile(html=html))
    assert any("linkedin.com/in/ada-lovelace" in link for link in report.linkedin_profiles)


def test_twitter_extraction() -> None:
    html = '<a href="https://twitter.com/acmehq">Twitter</a>'
    report = discover(make_profile(html=html))
    assert any("twitter.com/acmehq" in link for link in report.twitter_profiles)


def test_extra_pages_are_fetched(monkeypatch: pytest.MonkeyPatch) -> None:
    homepage = "<html><body><a href='/team'>Team</a></body></html>"
    team_html = """
    <section>
      <p>Priya Patel, Founder — priya@acme.example</p>
    </section>
    """

    class FakeResponse:
        def __init__(self, url: str, text: str) -> None:
            self.url = url
            self.text = text
            self.status_code = 200
            self.headers = {"content-type": "text/html"}

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def get(self, url: str) -> FakeResponse:
            if url.rstrip("/").endswith("/team"):
                return FakeResponse(url, team_html)
            return FakeResponse(url, "<html></html>")

        def close(self) -> None:
            return None

    monkeypatch.setattr("app.contact_discovery.service.httpx.Client", FakeClient)
    service = ContactDiscoveryService(fetch_extra_pages=True)
    report = service.discover(
        make_profile(
            html=homepage,
            internal_links=["https://acme.example/team"],
        )
    )
    assert any(page.endswith("/team") for page in report.pages_scanned)
    assert report.decision_makers_found >= 1
    assert report.best_contact is not None
    assert report.best_contact.email == "priya@acme.example"


def test_normalize_email() -> None:
    assert normalize_email("  Ada@Acme.Example ") == "ada@acme.example"
