from bs4 import BeautifulSoup

from app.contact_discovery.extractors import extract_emails_from_text, extract_mailto_emails
from app.contact_discovery.service import ContactDiscoveryService
from app.contact_discovery.validators import is_valid_email, normalize_email
from app.crawler.types import WebsiteProfile


def make_profile(html: str = "", emails: list[str] | None = None) -> WebsiteProfile:
    return WebsiteProfile(
        url="https://acme.example",
        final_url="https://acme.example/",
        title="Acme",
        emails=emails or [],
        metadata={"html": html, "external_links": [], "internal_links": []},
    )


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


def test_founder_extraction() -> None:
    html = """
    <section>
      <h2>Meet the team</h2>
      <p>Jane Founder is the Founder of Acme. Reach her at jane@acme.example</p>
    </section>
    """
    report = ContactDiscoveryService().discover(make_profile(html=html))
    assert any(
        contact.role == "Founder" and contact.email == "jane@acme.example"
        for contact in report.contacts
    )


def test_ceo_extraction() -> None:
    html = """
    <div>
      <p>John Smith, CEO</p>
      <a href="https://linkedin.com/in/john-smith">LinkedIn</a>
    </div>
    """
    report = ContactDiscoveryService().discover(make_profile(html=html))
    assert any(
        contact.role == "CEO" and contact.full_name == "John Smith" for contact in report.contacts
    )


def test_duplicate_removal() -> None:
    html = """
    <p>Support email support@acme.example</p>
    <a href="mailto:support@acme.example">Mail</a>
    """
    report = ContactDiscoveryService().discover(
        make_profile(html=html, emails=["support@acme.example"])
    )
    support_contacts = [c for c in report.contacts if c.email == "support@acme.example"]
    assert len(support_contacts) == 1
    assert report.emails.count("support@acme.example") == 1


def test_linkedin_extraction() -> None:
    html = '<a href="https://linkedin.com/in/ada-lovelace">Ada</a>'
    report = ContactDiscoveryService().discover(make_profile(html=html))
    assert any("linkedin.com/in/ada-lovelace" in link for link in report.linkedin_profiles)


def test_twitter_extraction() -> None:
    html = '<a href="https://twitter.com/acmehq">Twitter</a>'
    report = ContactDiscoveryService().discover(make_profile(html=html))
    assert any("twitter.com/acmehq" in link for link in report.twitter_profiles)


def test_support_email() -> None:
    report = ContactDiscoveryService().discover(
        make_profile(html="<p>Email support@acme.example</p>")
    )
    support = next(c for c in report.contacts if c.email == "support@acme.example")
    assert support.confidence == 0.55


def test_confidence_ordering() -> None:
    html = """
    <section>
      <p>Jane Founder, Founder - jane@acme.example</p>
      <p>Reach support@acme.example for help</p>
      <p>General contact@acme.example</p>
    </section>
    """
    report = ContactDiscoveryService().discover(make_profile(html=html))
    confidences = [contact.confidence for contact in report.contacts]
    assert confidences == sorted(confidences, reverse=True)
    assert report.contacts[0].confidence >= report.contacts[-1].confidence


def test_ignores_noreply_and_fake_emails() -> None:
    assert is_valid_email("noreply@acme.example") is False
    assert is_valid_email("privacy@acme.example") is False
    assert is_valid_email("user@example.com") is False
    assert normalize_email("Hello@Acme.Example") == "hello@acme.example"
