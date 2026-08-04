from app.company_profile.builder import CompanyProfileBuilder
from app.company_profile.types import CompanyProfile
from app.core.logger import get_logger
from app.crawler.types import WebsiteProfile


class CompanyProfileService:
    def __init__(self, builder: CompanyProfileBuilder | None = None) -> None:
        self.builder = builder or CompanyProfileBuilder()
        self.logger = get_logger(__name__)

    def extract(self, profile: WebsiteProfile) -> CompanyProfile:
        company_profile = self.builder.build(profile)
        self.logger.info(
            ("url=%s company=%s category=%s product_type=%s " "pricing=%s confidence=%.2f"),
            company_profile.source_url,
            company_profile.company_name,
            company_profile.business_category,
            company_profile.product_type,
            company_profile.pricing_model,
            company_profile.confidence,
        )
        return company_profile
