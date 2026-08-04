from collections import Counter

from app.contact_discovery.types import ContactCandidate
from app.email_patterns.rules import (
    GENERIC_LOCAL_PARTS,
    PATTERN_RULES,
    NameParts,
    PatternRule,
    normalize_name_token,
    split_contact_name,
)
from app.email_patterns.types import EmailPattern, EmailPatternReport


class EmailPatternGenerator:
    def infer_patterns_from_emails(
        self,
        emails: list[str],
        domain: str,
    ) -> dict[str, tuple[float, list[str]]]:
        inferred: dict[str, tuple[float, list[str]]] = {}
        domain = domain.lower()
        person_hits: Counter[str] = Counter()
        generic_hits: list[str] = []

        for email in emails:
            normalized = email.strip().lower()
            if "@" not in normalized:
                continue
            local_part, email_domain = normalized.rsplit("@", 1)
            if email_domain != domain:
                continue

            if local_part in GENERIC_LOCAL_PARTS:
                generic_hits.append(normalized)
                continue

            matched_pattern = self._match_local_part_to_pattern(local_part)
            if matched_pattern:
                person_hits[matched_pattern] += 1

        for pattern_name, count in person_hits.items():
            confidence = min(0.95, 0.8 + (0.05 * (count - 1)))
            inferred[pattern_name] = (
                confidence,
                [f"Inferred from existing personal email pattern ({count} match(es))"],
            )

        if generic_hits:
            for rule in PATTERN_RULES:
                current = inferred.get(rule.pattern_name)
                boost = 0.1
                evidence = [f"Domain mailbox in use: {address}" for address in generic_hits]
                if current:
                    inferred[rule.pattern_name] = (
                        min(0.98, current[0] + boost),
                        current[1] + evidence,
                    )
                else:
                    inferred[rule.pattern_name] = (
                        min(0.85, rule.base_confidence + boost),
                        evidence,
                    )

        return inferred

    def generate_for_contact(
        self,
        contact: ContactCandidate,
        domain: str,
        inferred: dict[str, tuple[float, list[str]]],
    ) -> list[EmailPattern]:
        parts = split_contact_name(
            full_name=contact.full_name,
            first_name=contact.first_name,
            last_name=contact.last_name,
        )
        if parts is None:
            return []

        patterns: list[EmailPattern] = []
        for rule in PATTERN_RULES:
            address = rule.builder(parts, domain)
            if not address:
                continue

            confidence, evidence = self._score_pattern(rule, inferred, parts)
            patterns.append(
                EmailPattern(
                    pattern_name=rule.pattern_name,
                    template=rule.template,
                    confidence=confidence,
                    generated_addresses=[address],
                    evidence=evidence,
                )
            )

        patterns.sort(key=lambda item: item.confidence, reverse=True)
        return patterns

    def build_report(
        self,
        *,
        domain: str,
        contacts: list[ContactCandidate],
        existing_emails: list[str],
    ) -> EmailPatternReport:
        inferred = self.infer_patterns_from_emails(existing_emails, domain)
        pattern_map: dict[str, EmailPattern] = {}
        candidates: list[str] = []
        evidence: list[str] = []

        if not contacts and not existing_emails:
            return EmailPatternReport(
                domain=domain,
                patterns=[],
                candidates=[],
                inferred_pattern=None,
                confidence=0.2,
                evidence=["No contacts or existing emails available"],
            )

        for contact in contacts:
            generated = self.generate_for_contact(contact, domain, inferred)
            for pattern in generated:
                candidates.extend(pattern.generated_addresses)
                existing = pattern_map.get(pattern.pattern_name)
                if existing is None or pattern.confidence > existing.confidence:
                    merged_addresses = list(
                        dict.fromkeys(
                            (existing.generated_addresses if existing else [])
                            + pattern.generated_addresses
                        )
                    )
                    pattern_map[pattern.pattern_name] = EmailPattern(
                        pattern_name=pattern.pattern_name,
                        template=pattern.template,
                        confidence=pattern.confidence,
                        generated_addresses=merged_addresses,
                        evidence=list(dict.fromkeys(pattern.evidence)),
                    )

        if inferred:
            evidence.append("Used existing company emails to improve pattern confidence")

        patterns = sorted(pattern_map.values(), key=lambda item: item.confidence, reverse=True)
        inferred_pattern = patterns[0].pattern_name if patterns else None
        confidence = patterns[0].confidence if patterns else (0.4 if existing_emails else 0.2)

        unique_candidates = list(dict.fromkeys(address.lower() for address in candidates))
        return EmailPatternReport(
            domain=domain,
            patterns=patterns,
            candidates=unique_candidates,
            inferred_pattern=inferred_pattern,
            confidence=confidence,
            evidence=evidence,
        )

    def _score_pattern(
        self,
        rule: PatternRule,
        inferred: dict[str, tuple[float, list[str]]],
        parts: NameParts,
    ) -> tuple[float, list[str]]:
        evidence = [f"Generated from contact name: {parts.first} {parts.last}".strip()]
        if rule.pattern_name in inferred:
            confidence, inferred_evidence = inferred[rule.pattern_name]
            return confidence, evidence + inferred_evidence

        if parts.last:
            return rule.base_confidence, evidence + ["Only name available for pattern generation"]
        return max(0.35, rule.base_confidence - 0.15), evidence + [
            "Partial name available for pattern generation"
        ]

    def _match_local_part_to_pattern(self, local_part: str) -> str | None:
        token = normalize_name_token(local_part.replace(".", " ").replace("_", " "))
        if "." in local_part:
            left, right = local_part.split(".", 1)
            if len(left) == 1 and right:
                return "f.lastname"
            if left and right:
                return "first.last"
        if "_" in local_part:
            left, right = local_part.split("_", 1)
            if left and right:
                return "first_last"
        if token and token.isalpha():
            # Ambiguous single-token personals are treated as firstname by default.
            return "firstname"
        return None
