from datetime import datetime, timezone

from app.contact_discovery.types import ContactCandidate, ContactDiscoveryReport
from app.email_patterns.service import EmailPatternService
from app.intelligence.service import LeadIntelligenceService
from app.qualification.types import QualificationResult
from app.schemas.company import CompanyResponse


def make_company(website: str = "acme.example") -> CompanyResponse:
    return CompanyResponse(
        id="company-1",
        name="Acme Labs",
        website=website,
        description="Workflow tools",
        industry="SaaS",
        source="producthunt",
        created_at=datetime.now(timezone.utc),
    )


def make_lead(
    *,
    contacts: list[ContactCandidate] | None = None,
    emails: list[str] | None = None,
) -> object:
    contact_list = contacts or []
    email_list = emails or []
    return LeadIntelligenceService().build(
        company=make_company(),
        contact_discovery=ContactDiscoveryReport(
            url="https://acme.example",
            contacts=contact_list,
            emails=email_list,
            contact_count=len(contact_list),
        ),
        qualification=QualificationResult(qualified=True, score=65),
        collector_name="producthunt",
    )


def test_single_founder() -> None:
    lead = make_lead(
        contacts=[
            ContactCandidate(
                full_name="Jane Founder",
                first_name="Jane",
                last_name="Founder",
                role="Founder",
                confidence=0.9,
            )
        ]
    )
    report = EmailPatternService().discover(lead)  # type: ignore[arg-type]

    assert report.domain == "acme.example"
    assert "jane.founder@acme.example" in report.unique_candidates
    assert "jane@acme.example" in report.unique_candidates
    assert report.confidence >= 0.5
    assert report.best_candidate is not None


def test_multiple_founders() -> None:
    lead = make_lead(
        contacts=[
            ContactCandidate(full_name="Jane Doe", first_name="Jane", last_name="Doe"),
            ContactCandidate(full_name="John Smith", first_name="John", last_name="Smith"),
        ]
    )
    report = EmailPatternService().discover(lead)  # type: ignore[arg-type]

    assert "jane.doe@acme.example" in report.unique_candidates
    assert "john.smith@acme.example" in report.unique_candidates
    assert len(report.unique_candidates) == len(set(report.unique_candidates))


def test_existing_support_email() -> None:
    lead = make_lead(
        contacts=[ContactCandidate(full_name="Jane Doe", first_name="Jane", last_name="Doe")],
        emails=["support@acme.example"],
    )
    report = EmailPatternService().discover(lead)  # type: ignore[arg-type]

    assert any(
        "Domain mailbox in use: support@acme.example" in " ".join(p.evidence)
        for p in report.patterns
    )
    assert report.confidence >= 0.55


def test_existing_hello_email() -> None:
    lead = make_lead(
        contacts=[
            ContactCandidate(full_name="Ada Lovelace", first_name="Ada", last_name="Lovelace")
        ],
        emails=["hello@acme.example"],
    )
    report = EmailPatternService().discover(lead)  # type: ignore[arg-type]
    assert report.confidence >= 0.55
    assert any("hello@acme.example" in " ".join(pattern.evidence) for pattern in report.patterns)


def test_duplicate_removal() -> None:
    lead = make_lead(
        contacts=[
            ContactCandidate(full_name="Jane Doe", first_name="Jane", last_name="Doe"),
            ContactCandidate(full_name="Jane Doe", first_name="Jane", last_name="Doe"),
        ]
    )
    report = EmailPatternService().discover(lead)  # type: ignore[arg-type]
    assert len(report.unique_candidates) == len(set(report.unique_candidates))


def test_confidence_ordering() -> None:
    lead = make_lead(
        contacts=[ContactCandidate(full_name="Jane Doe", first_name="Jane", last_name="Doe")],
        emails=["jane.doe@acme.example"],
    )
    report = EmailPatternService().discover(lead)  # type: ignore[arg-type]
    confidences = [pattern.confidence for pattern in report.patterns]
    assert confidences == sorted(confidences, reverse=True)
    assert report.inferred_pattern == "first.last"


def test_pattern_inference() -> None:
    lead = make_lead(
        contacts=[ContactCandidate(full_name="John Smith", first_name="John", last_name="Smith")],
        emails=["ada.lovelace@acme.example"],
    )
    report = EmailPatternService().discover(lead)  # type: ignore[arg-type]
    assert report.inferred_pattern == "first.last"
    first_last = next(
        pattern for pattern in report.patterns if pattern.pattern_name == "first.last"
    )
    assert first_last.confidence >= 0.8


def test_no_contacts() -> None:
    lead = make_lead(contacts=[], emails=[])
    report = EmailPatternService().discover(lead)  # type: ignore[arg-type]
    assert report.unique_candidates == []
    assert report.confidence <= 0.2
    assert report.primary_email is None
