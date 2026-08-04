from __future__ import annotations

from app.company_profile import extractors
from app.company_profile import rules as profile_rules
from app.company_profile.types import CompanyProfile
from app.crawler.types import WebsiteProfile


class CompanyProfileBuilder:
    def build(self, profile: WebsiteProfile) -> CompanyProfile:
        soup = extractors.extract_html_soup(profile)
        org_fields = extractors.extract_organization_fields(soup)
        corpus = extractors.build_signal_corpus(profile, soup)
        signals: list[str] = []

        company_name = extractors.extract_company_name(profile, soup)
        if not company_name and isinstance(org_fields.get("name"), str):
            company_name = str(org_fields["name"]).strip() or None

        tagline = extractors.extract_tagline(profile, soup)
        short_description = extractors.extract_short_description(profile, soup)
        if not short_description and isinstance(org_fields.get("description"), str):
            short_description = str(org_fields["description"]).strip() or None

        business_category, category_signals = profile_rules.infer_business_category(corpus)
        signals.extend(category_signals)

        industry, industry_signals = profile_rules.infer_industry(corpus)
        signals.extend(industry_signals)

        product_type, product_signals = profile_rules.infer_product_type(corpus)
        signals.extend(product_signals)

        target_audience, audience_signals = profile_rules.infer_target_audience(corpus)
        signals.extend(audience_signals)

        pricing_model, pricing_signals = profile_rules.infer_pricing_model(
            corpus,
            has_pricing_page=bool(profile.pricing_pages),
        )
        signals.extend(pricing_signals)

        primary_cta = extractors.extract_primary_cta(soup)
        headquarters = extractors.extract_headquarters(soup, org_fields)
        founded_year = extractors.extract_founded_year(soup, org_fields)
        social_links = extractors.extract_social_links(profile)

        filled = sum(
            1
            for value in (
                company_name,
                tagline,
                short_description,
                business_category,
                industry,
                product_type,
                target_audience,
                pricing_model,
                primary_cta,
                headquarters,
                founded_year,
            )
            if value is not None
        )
        confidence = round(min(1.0, filled / 11.0 + (0.05 if social_links else 0.0)), 2)

        return CompanyProfile(
            company_name=company_name,
            tagline=tagline,
            short_description=short_description,
            business_category=business_category,
            industry=industry,
            product_type=product_type,
            target_audience=target_audience,
            pricing_model=pricing_model,
            primary_cta=primary_cta,
            headquarters=headquarters,
            founded_year=founded_year,
            social_links=social_links,
            source_url=profile.final_url or profile.url,
            confidence=confidence,
            signals=signals,
        )
