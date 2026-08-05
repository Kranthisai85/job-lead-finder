from __future__ import annotations

from typing import Any

from app.company_profile.builder import CompanyProfileBuilder
from app.company_profile.service import CompanyProfileService
from app.crawler.types import SocialLinks, WebsiteProfile


def make_profile(
    html: str = "",
    *,
    title: str = "Linear",
    description: str | None = None,
    open_graph: dict[str, str] | None = None,
    twitter: dict[str, str] | None = None,
    social_links: SocialLinks | None = None,
    pricing_pages: list[str] | None = None,
) -> WebsiteProfile:
    metadata: dict[str, Any] = {
        "html": html,
        "open_graph": open_graph or {},
        "twitter": twitter or {},
        "headers": {},
    }
    return WebsiteProfile(
        url="https://linear.app",
        final_url="https://linear.app/",
        title=title,
        description=description,
        social_links=social_links or SocialLinks(),
        pricing_pages=pricing_pages or [],
        metadata=metadata,
        valid=True,
        status_code=200,
    )


LINEAR_HTML = """
<html>
  <head>
    <title>Linear – Issue tracking for modern software teams</title>
    <meta name="description"
          content="Linear builds modern issue tracking software for software teams." />
    <meta property="og:site_name" content="Linear" />
    <meta property="og:title" content="Linear" />
    <meta property="og:description" content="Issue tracking for modern software teams." />
    <script type="application/ld+json">
    {
      "@type": "Organization",
      "name": "Linear",
      "description": "Issue tracking for software teams",
      "foundingDate": "2019",
      "address": {
        "addressLocality": "San Francisco",
        "addressRegion": "CA",
        "addressCountry": "US"
      }
    }
    </script>
  </head>
  <body>
    <nav>Product Pricing Developers Docs</nav>
    <header class="hero">
      <h1>The issue tracking tool you'll enjoy using</h1>
      <p>Built for software teams and startups.</p>
      <a href="/signup">Start Free</a>
    </header>
    <footer>Headquarters: San Francisco, CA. Founded in 2019. Freemium SaaS for developers.</footer>
  </body>
</html>
"""


def test_extracts_company_name_and_description() -> None:
    profile = make_profile(
        LINEAR_HTML,
        open_graph={"og:site_name": "Linear", "og:description": "Issue tracking for teams"},
    )
    result = CompanyProfileService().extract(profile)

    assert result.company_name == "Linear"
    assert result.short_description is not None
    assert "issue tracking" in result.short_description.lower()


def test_infers_developer_tools_and_saas() -> None:
    profile = make_profile(LINEAR_HTML)
    result = CompanyProfileBuilder().build(profile)

    assert result.business_category == "Developer Tools"
    assert result.product_type in {"SaaS", "Platform"}
    assert result.target_audience in {"Developers", "Startups"}
    assert result.pricing_model == "Freemium"
    assert result.primary_cta == "Start Free"


def test_extracts_founded_year_and_headquarters() -> None:
    profile = make_profile(LINEAR_HTML)
    result = CompanyProfileService().extract(profile)

    assert result.founded_year == 2019
    assert result.headquarters is not None
    assert "San Francisco" in result.headquarters


def test_uses_profile_fields_without_html() -> None:
    profile = WebsiteProfile(
        url="https://acme.example",
        final_url="https://acme.example/",
        title="Acme Analytics",
        description="Analytics platform for marketing teams with freemium pricing",
        metadata={
            "open_graph": {
                "og:site_name": "Acme",
                "og:description": "Analytics for marketing teams",
            }
        },
        valid=True,
    )
    result = CompanyProfileService().extract(profile)

    assert result.company_name == "Acme"
    assert result.business_category in {"Analytics", "Marketing"}
    assert result.short_description is not None


def test_social_links_from_profile() -> None:
    profile = make_profile(
        "<html></html>",
        social_links=SocialLinks(
            twitter=["https://twitter.com/linear"],
            github=["https://github.com/linear"],
        ),
    )
    result = CompanyProfileService().extract(profile)
    assert result.social_links["twitter"] == ["https://twitter.com/linear"]
    assert result.social_links["github"] == ["https://github.com/linear"]
