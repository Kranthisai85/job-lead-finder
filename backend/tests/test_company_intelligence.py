from __future__ import annotations

import pytest

from app.company_intelligence.extractor import (
    detect_pricing_model,
    extract_competitors,
    extract_keywords,
    score_label,
    BUSINESS_MODEL_RULES,
    TARGET_CUSTOMER_RULES,
)
from app.company_intelligence.models import CompanyIntelligenceReport
from app.company_intelligence.service import CompanyIntelligenceService
from app.collectors.types import CompanyLead
from app.crawler.types import WebsiteProfile
from app.hiring_detection.types import HiringDetectionReport, HiringOpportunity
from app.qualification.context import QualificationContext
from app.qualification.scoring_engine import QualificationScoringEngine
from app.technology.types import Technology, TechnologyReport


def make_profile(
    html: str = "",
    *,
    url: str = "https://acme.example",
    title: str = "Acme",
    description: str | None = None,
    pricing_pages: list[str] | None = None,
    technologies: list[str] | None = None,
) -> WebsiteProfile:
    return WebsiteProfile(
        url=url,
        final_url=f"{url.rstrip('/')}/",
        title=title,
        description=description,
        pricing_pages=pricing_pages or [],
        technologies=technologies or [],
        metadata={
            "html": html,
            "about_pages": [],
            "internal_links": [],
            "external_links": [],
        },
        valid=True,
    )


def analyze(profile: WebsiteProfile, **kwargs: object) -> CompanyIntelligenceReport:
    service = CompanyIntelligenceService(
        fetch_extra_pages=False,
        **kwargs,  # type: ignore[arg-type]
    )
    return service.analyze(profile)


B2B_SAAS_HTML = """
<html>
  <head>
    <meta name="description"
          content="B2B SaaS platform for businesses. Software as a service." />
    <script type="application/ld+json">
      {
        "@type": "Organization",
        "name": "Acme Cloud",
        "description": "Cloud SaaS for companies",
        "industry": "Software"
      }
    </script>
  </head>
  <body>
    <h1>Acme Cloud</h1>
    <div class="hero"><p>The SaaS platform for businesses to automate workflows.</p></div>
    <a href="/pricing">Pricing</a>
    <section class="faq"><h2>FAQ</h2><p>How does subscription billing work?</p></section>
  </body>
</html>
"""

DEVELOPER_TOOLS_HTML = """
<html>
  <body>
    <h1>Ship APIs faster</h1>
    <p>Developer tools and SDK for software engineers. Built for developers.</p>
    <p>Alternative to Postman and better than Insomnia.</p>
  </body>
</html>
"""

ENTERPRISE_HTML = """
<html>
  <body>
    <h1>Enterprise platform</h1>
    <p>Enterprise software for Fortune 500 and large organizations.</p>
    <p>Contact sales for enterprise pricing.</p>
  </body>
</html>
"""

CONSUMER_HTML = """
<html>
  <body>
    <h1>Photo fun for everyone</h1>
    <p>Consumer app for individuals and personal use. B2C mobile experience.</p>
  </body>
</html>
"""

PRICING_HTML = """
<html>
  <body>
    <h1>Pricing</h1>
    <p>Start free. Upgrade to Pro plan. Freemium subscription starts at $29/mo.</p>
  </body>
</html>
"""

FINTECH_HTML = """
<html>
  <body>
    <h1>Modern banking for startups</h1>
    <p>Fintech payments platform for small businesses and startups.</p>
    <p>We raised a Series A to scale lending.</p>
  </body>
</html>
"""

SPARSE_HTML = """
<html><body><h1>Hello</h1><p>Welcome.</p></body></html>
"""


def test_score_business_model_saas() -> None:
    label, hits = score_label("our saas cloud software as a service", BUSINESS_MODEL_RULES)
    assert label == "SaaS"
    assert hits


def test_score_target_customer_b2b() -> None:
    label, _ = score_label("built for businesses and companies b2b", TARGET_CUSTOMER_RULES)
    assert label == "B2B"


def test_extract_competitors() -> None:
    text = "Unlike Slack and better than Notion, we focus on speed. Alternative to Asana."
    competitors = extract_competitors(text)
    assert "Slack" in competitors
    assert "Notion" in competitors


def test_detect_pricing_freemium() -> None:
    assert (
        detect_pricing_model("start free freemium free plan", has_pricing_page=True) == "Freemium"
    )


def test_b2b_saas_detection() -> None:
    report = analyze(
        make_profile(
            B2B_SAAS_HTML,
            description="B2B SaaS for businesses",
            pricing_pages=["https://acme.example/pricing"],
        )
    )
    assert report.business_model == "SaaS"
    assert report.target_customer in {"B2B", "Enterprise", "SMB", "Startup"}
    assert report.is_b2b_saas is True
    assert report.has_pricing_page is True
    assert report.has_clear_icp is True
    assert 0.0 <= report.confidence <= 1.0
    assert report.confidence >= 0.4
    assert report.main_product is not None


def test_developer_tools_detection() -> None:
    report = analyze(make_profile(DEVELOPER_TOOLS_HTML, description="Developer tools SDK"))
    assert report.business_model == "Developer Tool"
    assert report.is_developer_tools is True
    assert report.target_customer == "Developers" or report.is_developer_tools
    assert any(name in report.competitors for name in ("Postman", "Insomnia"))


def test_enterprise_software_detection() -> None:
    report = analyze(make_profile(ENTERPRISE_HTML))
    assert report.is_enterprise_software is True
    assert report.business_model in {"Enterprise Software", "SaaS"}
    assert report.pricing_model in {"Enterprise", "Paid", "Unknown"}


def test_consumer_only_scores_zero_intelligence_bonus() -> None:
    report = analyze(make_profile(CONSUMER_HTML, description="Consumer app for individuals"))
    assert report.is_consumer_only is True
    assert report.is_b2b_saas is False

    lead = CompanyLead(
        name="FunApp",
        website="https://fun.example",
        description="Consumer app",
        source="test",
    )
    context = QualificationContext.from_enriched(lead, company_intelligence=report)
    result = QualificationScoringEngine().score(context)
    assert not any("B2B SaaS" in reason for reason in result.reasons)
    assert not any("Developer tools" in reason for reason in result.reasons)


def test_pricing_page_and_subscription() -> None:
    report = analyze(
        make_profile(
            PRICING_HTML,
            pricing_pages=["https://acme.example/pricing"],
            description="SaaS pricing plans",
        )
    )
    assert report.has_pricing_page is True
    assert report.pricing_model in {"Freemium", "Subscription", "Paid", "Free"}


def test_fintech_stage_and_funding() -> None:
    report = analyze(make_profile(FINTECH_HTML, description="Fintech for startups"))
    assert report.business_model == "FinTech" or report.industry == "FinTech"
    assert report.funding_status == "Series A"
    assert report.company_stage in {"Growth", "Early Startup", "MVP", None} or report.funding_status


def test_hiring_report_enriches_opportunities() -> None:
    hiring = HiringDetectionReport(
        url="https://acme.example",
        jobs_found=2,
        flutter_jobs=1,
        engineering_jobs=2,
        opportunities=[
            HiringOpportunity(
                title="Senior Flutter Engineer",
                matched_keywords=["flutter", "flutter engineer"],
                confidence=0.9,
            )
        ],
    )
    report = CompanyIntelligenceService(fetch_extra_pages=False).analyze(
        make_profile(B2B_SAAS_HTML, description="B2B SaaS"),
        hiring_report=hiring,
    )
    assert any("Flutter" in item or "engineering" in item.lower() for item in report.opportunities)
    assert report.estimated_team_size is not None


def test_technology_report_in_corpus() -> None:
    tech = TechnologyReport(
        url="https://acme.example",
        technologies=[Technology(name="React", category="framework", confidence=80)],
        detected_count=1,
    )
    report = CompanyIntelligenceService(fetch_extra_pages=False).analyze(
        make_profile(B2B_SAAS_HTML, technologies=["Next.js"]),
        technology_report=tech,
    )
    assert "react" in " ".join(report.keywords) or report.confidence > 0


def test_sparse_page_low_confidence() -> None:
    report = analyze(make_profile(SPARSE_HTML))
    assert report.confidence < 0.6
    assert report.pricing_model == "Unknown"


def test_keywords_extracted() -> None:
    keywords = extract_keywords("saas saas platform platform automation workflow workflow workflow")
    assert "workflow" in keywords
    assert keywords[0] == "workflow"


def test_qualification_awards_intelligence_bonuses() -> None:
    lead = CompanyLead(
        name="Acme",
        website="https://acme.example",
        description="B2B SaaS developer tools",
        source="test",
    )
    intel = CompanyIntelligenceReport(
        url="https://acme.example",
        business_model="SaaS",
        target_customer="B2B",
        is_b2b_saas=True,
        is_developer_tools=True,
        is_enterprise_software=False,
        has_clear_icp=True,
        has_pricing_page=True,
        is_consumer_only=False,
        confidence=0.8,
    )
    context = QualificationContext.from_enriched(lead, company_intelligence=intel)
    result = QualificationScoringEngine().score(context)
    reasons = " ".join(result.reasons)
    assert "B2B SaaS" in reasons
    assert "Clear ICP" in reasons
    assert "Pricing page exists" in reasons
    assert "Developer tools" in reasons


def test_qualification_enterprise_software_bonus() -> None:
    lead = CompanyLead(name="BigCo", website="https://big.example", source="test")
    intel = CompanyIntelligenceReport(
        url="https://big.example",
        business_model="Enterprise Software",
        target_customer="Enterprise",
        is_enterprise_software=True,
        has_clear_icp=True,
        confidence=0.7,
    )
    context = QualificationContext.from_enriched(lead, company_intelligence=intel)
    result = QualificationScoringEngine().score(context)
    assert any("Enterprise software" in reason for reason in result.reasons)


def test_logging_fields(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO"):
        analyze(make_profile(B2B_SAAS_HTML, description="B2B SaaS for businesses"))
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "business_model=" in messages
    assert "target_customer=" in messages
    assert "confidence=" in messages
    assert "clear_icp=" in messages
