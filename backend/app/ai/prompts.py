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


NATURAL_WRITING_GUIDE = """
Write like a real person sending a short cold email from their inbox — not like ChatGPT,
a sales sequence, or a marketing template.

Tone rules:
- Sound casual-professional and specific. Prefer short sentences and plain words.
- Subject should feel human (curious, concrete, lightly incomplete is fine). Max ~8 words.
  Good: "quick thought on {company} mobile" / "native app for {company}?"
  Bad: "Inquiry About Native Mobile App Development" / "Exploring Strategic Partnership Opportunities"
- Opening: greet the person by first name if known, otherwise the company. One short line.
- Body: 2–4 short sentences. Mention one real fact from the company data, then one clear idea.
- CTA: one soft question. No pressure, no "synergy", no "next steps for our partnership".
- signature must be exactly "{{sender_name}}"

Hard bans (never write these):
- "I hope this email finds you well"
- "Greetings from ..."
- "We recently launched ..." / "It's amazing to see ..."
- "leverage", "utilize", "synergies", "cutting-edge", "robust", "seamless", "elevate"
- "Would X be open to a short conversation about next steps for Y"
- Bullet lists, markdown, emojis, exclamation overload, or fake personalization

Facts:
- Use only company facts provided below.
- Do not invent contacts, technologies, websites, or Flutter/Dart evidence.
- If Flutter/Dart evidence is "no", do not claim they already use Flutter/Dart.
""".strip()

EMAIL_JSON_SCHEMA = """
Return ONLY a JSON object with exactly these keys (plain JSON, no markdown fences):
{"subject":"string","opening":"string","body":"string","cta":"string","signature":"{{sender_name}}"}
Keep each value concise and human-sounding. Do not include explanations or extra keys.
""".strip()

FOLLOWUP_JSON_SCHEMA = """
Return ONLY a JSON object with exactly these keys (plain JSON, no markdown fences):
{"subject":"string","opening":"string","body":"string","cta":"string","signature":"{{sender_name}}"}
Keep each value concise and human-sounding. Do not include explanations or extra keys.
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
            "Write one cold outreach email offering Flutter/mobile help. "
            "It must read as if a founder typed it quickly between meetings — "
            "natural, specific, and not AI-generated.\n\n"
            f"{NATURAL_WRITING_GUIDE}"
        ),
        context=context,
        schema=EMAIL_JSON_SCHEMA,
    )


def build_subject_prompt(context: EmailPromptContext) -> str:
    return _format_prompt(
        task=(
            "Write only a natural email subject line (max 8 words). "
            "It should look human, not like a marketing campaign.\n\n"
            f"{NATURAL_WRITING_GUIDE}"
        ),
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
            f"Write a short, human follow-up sent {days_since_sent} days after "
            f'the original email with subject "{previous_subject}". '
            "Keep it light — bump + one sentence reason to reply. No guilt trips.\n\n"
            f"{NATURAL_WRITING_GUIDE}"
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

Use the facts below as raw notes only. Rewrite them in your own words — do not paste
template phrases from "Value proposition", "Suggested CTA", or "Personalized opening".

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
