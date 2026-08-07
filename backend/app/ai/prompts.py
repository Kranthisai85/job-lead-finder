from __future__ import annotations

import json
from dataclasses import dataclass

from app.company_profile.types import CompanyProfile
from app.contact_discovery.types import ContactDiscoveryReport
from app.personalization.types import PersonalizedEmailContext
from app.pipeline.types import CompleteLead
from app.validation.types import compute_lead_score


@dataclass(frozen=True)
class EmailPromptContext:
    company_name: str
    company_website: str
    company_summary: str
    technologies: list[str]
    industry: str | None
    category: str | None
    contacts_summary: str
    mobile_opportunity: str
    lead_score: float
    is_flutter_lead: bool
    personalized_context: PersonalizedEmailContext


EMAIL_JSON_SCHEMA = """
Return ONLY a JSON object with exactly these keys (plain JSON, no markdown fences):
{"subject":"string","opening":"string","body":"string","cta":"string","signature":"{{sender_name}}"}
Keep each value concise. Do not include explanations or extra keys.
""".strip()

FOLLOWUP_JSON_SCHEMA = """
Return ONLY a JSON object with exactly these keys (plain JSON, no markdown fences):
{"subject":"string","opening":"string","body":"string","cta":"string","signature":"{{sender_name}}"}
Keep each value concise. Do not include explanations or extra keys.
""".strip()

DEFAULT_EMAIL_REQUIRED_FIELDS: tuple[str, ...] = ("subject", "opening", "body", "cta")
SUBJECT_ONLY_REQUIRED_FIELDS: tuple[str, ...] = ("subject",)


def _contacts_summary(contacts: ContactDiscoveryReport | None) -> str:
    if contacts is None or not contacts.contacts:
        if contacts and contacts.emails:
            return f"Emails found: {', '.join(contacts.emails[:3])}"
        return "No contacts discovered"
    lines: list[str] = []
    for contact in contacts.contacts[:5]:
        parts = [contact.full_name or "Unknown"]
        if contact.role:
            parts.append(f"({contact.role})")
        if contact.email:
            parts.append(f"<{contact.email}>")
        lines.append(" ".join(parts))
    return "; ".join(lines)


def _lead_score(lead: CompleteLead, context: PersonalizedEmailContext) -> float:
    qualification_score = 0
    if lead.qualification_report is not None:
        qualification_score = lead.qualification_report.score
    elif lead.lead_intelligence is not None:
        qualification_score = lead.lead_intelligence.qualification_score

    contact_emails = len(lead.contacts.emails) if lead.contacts else 0
    technology_count = len(context.technology_names)
    return compute_lead_score(
        qualification_score=qualification_score,
        contact_emails_found=contact_emails,
        technology_count=technology_count,
        mobile_app=context.has_mobile_app,
        is_good_lead=context.is_flutter_lead,
    )


def build_prompt_context(
    lead: CompleteLead,
    personalized: PersonalizedEmailContext,
) -> EmailPromptContext:
    profile: CompanyProfile | None = lead.company_profile
    website = (lead.startup.website or "").strip()
    if not website and lead.lead_intelligence is not None:
        website = (lead.lead_intelligence.company.website or "").strip()
    return EmailPromptContext(
        company_name=personalized.company_name,
        company_website=website,
        company_summary=personalized.company_summary,
        technologies=list(personalized.technology_names),
        industry=profile.industry if profile else None,
        category=profile.business_category if profile else None,
        contacts_summary=_contacts_summary(lead.contacts),
        mobile_opportunity=personalized.mobile_app_opportunity,
        lead_score=_lead_score(lead, personalized),
        is_flutter_lead=bool(personalized.is_flutter_lead),
        personalized_context=personalized,
    )


def build_email_prompt(context: EmailPromptContext) -> str:
    return _format_prompt(
        task=(
            "Write a concise, professional cold outreach email for a Flutter/mobile "
            "development agency. Use only the company facts provided below. "
            "Do not invent contacts, technologies, websites, or Flutter/Dart evidence."
        ),
        context=context,
        schema=EMAIL_JSON_SCHEMA,
    )


def build_subject_prompt(context: EmailPromptContext) -> str:
    return _format_prompt(
        task="Write only a compelling email subject line (max 12 words).",
        context=context,
        schema='Return ONLY JSON: {"subject":"string"}',
    )


def build_followup_prompt(
    context: EmailPromptContext,
    *,
    previous_subject: str,
    days_since_sent: int = 3,
) -> str:
    base = _format_prompt(
        task=(
            f"Write a polite follow-up email sent {days_since_sent} days after "
            f'the original message with subject "{previous_subject}".'
        ),
        context=context,
        schema=FOLLOWUP_JSON_SCHEMA,
    )
    return base


def _format_prompt(*, task: str, context: EmailPromptContext, schema: str) -> str:
    technologies = ", ".join(context.technologies) if context.technologies else "Unknown"
    industry = context.industry or "Unknown"
    category = context.category or "Unknown"
    website = context.company_website or "Unknown"
    flutter_evidence = "yes" if context.is_flutter_lead else "no"
    personalized = context.personalized_context

    prompt = f"""
{task}

Company: {context.company_name}
Website: {website}
Company summary: {context.company_summary}
Industry: {industry}
Category: {category}
Technologies: {technologies}
Contacts: {context.contacts_summary}
Mobile opportunity: {context.mobile_opportunity}
Flutter/Dart evidence: {flutter_evidence}
Lead score: {context.lead_score:.1f}
Qualification: {personalized.qualification_summary}
Value proposition: {personalized.suggested_value_proposition}
Suggested CTA: {personalized.cta_recommendation}
Personalized opening: {personalized.personalized_opening}

{schema}
""".strip()
    return prompt


def parse_email_json(
    raw: str,
    *,
    required_fields: tuple[str, ...] = DEFAULT_EMAIL_REQUIRED_FIELDS,
) -> dict[str, str]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(line for line in lines if not line.strip().startswith("```"))
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in model response")
    payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Model response JSON must be an object")
    result = {str(key): str(value) for key, value in payload.items()}
    missing = [field for field in required_fields if not result.get(field, "").strip()]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")
    for value in result.values():
        if "```" in value:
            raise ValueError("Model response must not contain markdown code fences")
    return result
