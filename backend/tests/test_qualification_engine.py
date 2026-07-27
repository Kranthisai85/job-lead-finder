from datetime import datetime, timezone
from typing import Any

from app.collectors.types import CompanyLead
from app.qualification.engine import QualificationEngine, build_default_engine
from app.qualification.rules import (
    ALL_RULE_NAMES,
    CompanyNameExistsRule,
    DescriptionExistsRule,
    DescriptionLengthRule,
    HasTopicRule,
    NotGithubIoRule,
    NotLocalhostRule,
    NotNetlifyAppRule,
    NotNotionSiteRule,
    NotVercelAppRule,
    WebsiteExistsRule,
)
from app.qualification.service import QualificationService


def make_lead(**overrides: Any) -> CompanyLead:
    base: dict[str, Any] = {
        "name": "Acme Labs",
        "website": "acme.example",
        "description": "A sufficiently detailed description for lead qualification scoring.",
        "source": "producthunt",
        "tags": ["SaaS"],
        "discovered_at": datetime.now(timezone.utc),
        "metadata": {},
    }
    base.update(overrides)
    return CompanyLead(**base)


def build_engine(
    *,
    passing_score: int | None = None,
    enabled_rules: set[str] | None = None,
) -> QualificationEngine:
    return build_default_engine(
        passing_score=passing_score,
        enabled_rules=enabled_rules,
    )


def test_website_exists_rule() -> None:
    passed = WebsiteExistsRule().evaluate(make_lead())
    failed = WebsiteExistsRule().evaluate(make_lead(website=""))

    assert passed.points == 20
    assert failed.blocking is True


def test_company_name_exists_rule() -> None:
    passed = CompanyNameExistsRule().evaluate(make_lead())
    failed = CompanyNameExistsRule().evaluate(make_lead(name=""))

    assert passed.points == 10
    assert failed.blocking is True


def test_description_exists_rule() -> None:
    passed = DescriptionExistsRule().evaluate(make_lead())
    failed = DescriptionExistsRule().evaluate(make_lead(description=None))

    assert passed.points == 10
    assert failed.points == 0


def test_not_localhost_rule() -> None:
    passed = NotLocalhostRule().evaluate(make_lead(website="acme.example"))
    failed = NotLocalhostRule().evaluate(make_lead(website="localhost:3000"))

    assert passed.blocking is False
    assert failed.blocking is True


def test_not_github_io_rule() -> None:
    failed = NotGithubIoRule().evaluate(make_lead(website="demo.github.io"))
    assert failed.blocking is True


def test_not_vercel_app_rule() -> None:
    failed = NotVercelAppRule().evaluate(make_lead(website="demo.vercel.app"))
    assert failed.blocking is True


def test_not_netlify_app_rule() -> None:
    failed = NotNetlifyAppRule().evaluate(make_lead(website="demo.netlify.app"))
    assert failed.blocking is True


def test_not_notion_site_rule() -> None:
    failed = NotNotionSiteRule().evaluate(make_lead(website="demo.notion.site"))
    assert failed.blocking is True


def test_description_length_rule() -> None:
    passed = DescriptionLengthRule().evaluate(make_lead())
    failed = DescriptionLengthRule().evaluate(make_lead(description="Too short"))

    assert passed.points == 15
    assert failed.points == 0


def test_has_topic_rule() -> None:
    passed = HasTopicRule().evaluate(make_lead(tags=["AI"]))
    failed = HasTopicRule().evaluate(make_lead(tags=[]))

    assert passed.points == 10
    assert failed.points == 0


def test_score_calculation_caps_at_100() -> None:
    engine = build_engine()
    result = engine.qualify(make_lead())

    assert result.score == 65
    assert result.qualified is True


def test_passing_score_threshold() -> None:
    engine = build_engine(passing_score=50)
    result = engine.qualify(
        make_lead(
            description="Short desc",
            tags=[],
        )
    )

    assert result.score == 40
    assert result.qualified is False


def test_failing_due_to_blocking_rule() -> None:
    engine = build_engine()
    result = engine.qualify(make_lead(website="demo.vercel.app"))

    assert result.qualified is False
    assert "Website uses vercel.app" in result.warnings


def test_disabled_rules() -> None:
    engine = build_engine(enabled_rules={"website_exists", "company_name_exists"})

    result = engine.qualify(make_lead(description=None, tags=[]))

    assert result.score == 30
    assert result.qualified is False


def test_custom_passing_score() -> None:
    engine = build_engine(passing_score=30, enabled_rules=set(ALL_RULE_NAMES))
    result = engine.qualify(make_lead(description="Short", tags=[]))

    assert result.score == 40
    assert result.qualified is True


def test_qualification_service_filters_leads() -> None:
    service = QualificationService(build_engine(passing_score=50))
    leads = [
        make_lead(name="Qualified Co"),
        make_lead(name="Low Score Co", description="Short", tags=[]),
    ]

    qualified = service.filter_qualified(leads)

    assert len(qualified) == 1
    assert qualified[0].name == "Qualified Co"
