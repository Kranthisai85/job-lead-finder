from app.core.logger import get_logger
from app.email_patterns.generator import EmailPatternGenerator
from app.email_patterns.types import EmailPatternReport
from app.intelligence.types import LeadIntelligence
from app.utils.url import normalize_website


class EmailPatternService:
    def __init__(self, generator: EmailPatternGenerator | None = None) -> None:
        self.generator = generator or EmailPatternGenerator()
        self.logger = get_logger(__name__)

    def discover(self, lead: LeadIntelligence) -> EmailPatternReport:
        domain = self._extract_domain(lead)
        contacts = lead.contact_discovery.contacts if lead.contact_discovery else []
        existing_emails = list(lead.contact_discovery.emails) if lead.contact_discovery else []
        if lead.primary_email and lead.primary_email not in existing_emails:
            existing_emails.append(lead.primary_email)

        named_contacts = [
            contact
            for contact in contacts
            if contact.full_name or contact.first_name or contact.last_name
        ]

        report = self.generator.build_report(
            domain=domain,
            contacts=named_contacts,
            existing_emails=existing_emails,
        )
        self.logger.info(
            ("company=%s domain=%s inferred_pattern=%s confidence=%.2f " "candidate_count=%d"),
            lead.company.name,
            report.domain,
            report.inferred_pattern,
            report.confidence,
            len(report.unique_candidates),
        )
        return report

    @staticmethod
    def _extract_domain(lead: LeadIntelligence) -> str:
        website = lead.company.website or ""
        domain = normalize_website(website)
        if domain:
            return domain
        if lead.website_profile and lead.website_profile.final_url:
            return normalize_website(lead.website_profile.final_url)
        return "unknown.example"
