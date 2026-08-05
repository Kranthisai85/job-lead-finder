from __future__ import annotations

from app.contact_discovery.types import (
    CompanyDecisionMaker,
    ContactCandidate,
    ContactDiscoveryReport,
    DiscoverySource,
)
from app.contact_discovery.validators import (
    is_decision_maker_role,
    is_fake_contact_name,
    is_generic_email_contact,
    is_valid_email,
    normalize_email,
    rank_contact,
)


class ContactDiscoveryEngine:
    def merge_contacts(self, contacts: list[ContactCandidate]) -> list[ContactCandidate]:
        merged: dict[str, ContactCandidate] = {}

        for contact in contacts:
            if contact.full_name and is_fake_contact_name(contact.full_name):
                continue
            working = contact
            if working.email and not is_valid_email(working.email):
                working = working.model_copy(update={"email": None})
                if not any([working.full_name, working.linkedin, working.github, working.twitter]):
                    continue

            match_key = None
            for key in self._identity_keys(working):
                if key in merged:
                    match_key = key
                    break

            if match_key is None:
                primary = self._contact_key(working)
                merged[primary] = working
                continue

            combined = self._merge_pair(merged[match_key], working)
            # Replace all keys that pointed at the old contact.
            stale_keys = [key for key, value in merged.items() if value is merged[match_key]]
            for key in stale_keys:
                del merged[key]
            primary = self._contact_key(combined)
            merged[primary] = combined
            for key in self._identity_keys(combined):
                merged[key] = combined

        # Unique contacts
        unique: dict[str, ContactCandidate] = {}
        for contact in merged.values():
            unique[self._contact_key(contact)] = contact

        results: list[ContactCandidate] = []
        for contact in unique.values():
            score, priority, confidence = rank_contact(
                email=contact.email,
                role=contact.role,
                linkedin=contact.linkedin,
                github=contact.github,
                full_name=contact.full_name,
            )
            results.append(
                contact.model_copy(
                    update={
                        "contact_score": score,
                        "contact_priority": priority,
                        "confidence": confidence,
                        "company_role": contact.company_role or contact.role,
                        "discovery_source": contact.discovery_source
                        or DiscoverySource.MERGED.value,
                    }
                )
            )

        results.sort(
            key=lambda item: (
                -item.contact_score,
                item.contact_priority,
                -(item.confidence or 0.0),
            )
        )
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
        pages_scanned: list[str] | None = None,
    ) -> ContactDiscoveryReport:
        cleaned_emails = sorted(
            {normalize_email(email) for email in emails if is_valid_email(email)}
        )
        merged_contacts = self.merge_contacts(contacts)

        decision_keys: set[str] = set()
        decision_candidates: list[ContactCandidate] = []
        for contact in merged_contacts:
            if is_decision_maker_role(contact.role) or (
                contact.email
                and contact.email.split("@", 1)[0].lower() in {"founder", "ceo", "cto", "hiring"}
            ):
                decision_candidates.append(contact)
                decision_keys.add(self._contact_key(contact))

        generic_contacts = [
            contact
            for contact in merged_contacts
            if self._contact_key(contact) not in decision_keys
            and is_generic_email_contact(
                email=contact.email,
                role=contact.role,
                full_name=contact.full_name,
            )
        ]

        non_generic = [
            contact
            for contact in merged_contacts
            if self._contact_key(contact) not in {self._contact_key(g) for g in generic_contacts}
        ]
        ranked_for_best = decision_candidates or non_generic or generic_contacts
        best = ranked_for_best[0] if ranked_for_best else None

        decision_makers = [
            CompanyDecisionMaker(
                name=(
                    contact.display_name
                    or (contact.email.split("@", 1)[0] if contact.email else "Unknown")
                ),
                role=contact.role,
                email=contact.email,
                linkedin=contact.linkedin,
                github=contact.github,
                twitter=contact.twitter,
                confidence=contact.confidence,
                source_page=contact.source_page,
                contact_score=contact.contact_score,
                discovery_source=contact.discovery_source,
                contact_priority=contact.contact_priority,
            )
            for contact in decision_candidates
            if contact.display_name or contact.email or contact.linkedin
        ]

        return ContactDiscoveryReport(
            url=url,
            contacts=merged_contacts,
            decision_makers=decision_makers,
            generic_contacts=generic_contacts,
            emails=cleaned_emails,
            linkedin_profiles=sorted(set(linkedin_profiles)),
            twitter_profiles=sorted(set(twitter_profiles)),
            github_profiles=sorted(set(github_profiles)),
            contact_count=len(merged_contacts),
            decision_makers_found=len(decision_makers),
            generic_contacts_found=len(generic_contacts),
            best_contact=best,
            best_contact_score=best.contact_score if best else None,
            pages_scanned=list(pages_scanned or []),
        )

    def _identity_keys(self, contact: ContactCandidate) -> list[str]:
        keys: list[str] = []
        if contact.email:
            keys.append(f"email:{normalize_email(contact.email)}")
        if contact.linkedin:
            keys.append(f"linkedin:{contact.linkedin.lower().rstrip('/')}")
        if contact.github:
            keys.append(f"github:{contact.github.lower().rstrip('/')}")
        if contact.full_name and contact.role:
            keys.append(f"name-role:{contact.full_name.lower()}:{contact.role.lower()}")
        return keys

    @staticmethod
    def _contact_key(contact: ContactCandidate) -> str:
        if contact.email:
            return f"email:{normalize_email(contact.email)}"
        if contact.linkedin:
            return f"linkedin:{contact.linkedin.lower().rstrip('/')}"
        if contact.github:
            return f"github:{contact.github.lower().rstrip('/')}"
        if contact.full_name and contact.role:
            return f"name-role:{contact.full_name.lower()}:{contact.role.lower()}"
        if contact.full_name:
            return f"name:{contact.full_name.lower()}"
        return f"anon:{id(contact)}"

    @staticmethod
    def _merge_pair(left: ContactCandidate, right: ContactCandidate) -> ContactCandidate:
        score = max(left.contact_score, right.contact_score)
        priority = min(left.contact_priority, right.contact_priority)
        return ContactCandidate(
            full_name=left.full_name or right.full_name,
            first_name=left.first_name or right.first_name,
            last_name=left.last_name or right.last_name,
            email=left.email or right.email,
            role=left.role or right.role,
            company_role=left.company_role or right.company_role or left.role or right.role,
            linkedin=left.linkedin or right.linkedin,
            github=left.github or right.github,
            twitter=left.twitter or right.twitter,
            source_page=left.source_page or right.source_page,
            discovery_source=left.discovery_source or right.discovery_source,
            contact_score=score,
            contact_priority=priority,
            confidence=max(left.confidence, right.confidence),
        )
