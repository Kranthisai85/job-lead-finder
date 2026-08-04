from app.contact_discovery.types import ContactCandidate, ContactDiscoveryReport
from app.contact_discovery.validators import is_valid_email, normalize_email, score_contact


class ContactDiscoveryEngine:
    def merge_contacts(self, contacts: list[ContactCandidate]) -> list[ContactCandidate]:
        merged: dict[str, ContactCandidate] = {}

        for contact in contacts:
            key = self._contact_key(contact)
            existing = merged.get(key)
            if existing is None:
                merged[key] = contact
                continue
            merged[key] = self._merge_pair(existing, contact)

        results = list(merged.values())
        for contact in results:
            contact.confidence = score_contact(
                email=contact.email,
                role=contact.role,
                linkedin=contact.linkedin,
            )
        results.sort(key=lambda item: item.confidence, reverse=True)
        return results

    def build_report(
        self,
        *,
        url: str,
        contacts: list[ContactCandidate],
        emails: list[str],
        linkedin_profiles: list[str],
        twitter_profiles: list[str],
        github_profiles: list[str],
    ) -> ContactDiscoveryReport:
        cleaned_emails = sorted(
            {normalize_email(email) for email in emails if is_valid_email(email)}
        )
        merged_contacts = self.merge_contacts(contacts)
        return ContactDiscoveryReport(
            url=url,
            contacts=merged_contacts,
            emails=cleaned_emails,
            linkedin_profiles=sorted(set(linkedin_profiles)),
            twitter_profiles=sorted(set(twitter_profiles)),
            github_profiles=sorted(set(github_profiles)),
            contact_count=len(merged_contacts),
        )

    @staticmethod
    def _contact_key(contact: ContactCandidate) -> str:
        if contact.email:
            return f"email:{normalize_email(contact.email)}"
        if contact.linkedin:
            return f"linkedin:{contact.linkedin.lower().rstrip('/')}"
        if contact.full_name and contact.role:
            return f"name-role:{contact.full_name.lower()}:{contact.role.lower()}"
        if contact.full_name:
            return f"name:{contact.full_name.lower()}"
        return f"anon:{id(contact)}"

    @staticmethod
    def _merge_pair(left: ContactCandidate, right: ContactCandidate) -> ContactCandidate:
        return ContactCandidate(
            full_name=left.full_name or right.full_name,
            first_name=left.first_name or right.first_name,
            last_name=left.last_name or right.last_name,
            email=left.email or right.email,
            role=left.role or right.role,
            linkedin=left.linkedin or right.linkedin,
            twitter=left.twitter or right.twitter,
            source_page=left.source_page or right.source_page,
            confidence=max(left.confidence, right.confidence),
        )
