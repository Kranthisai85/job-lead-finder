from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.company_profile.types import CompanyProfile
from app.contact_discovery.types import ContactDiscoveryReport
from app.contact_discovery.validators import normalize_person_name
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
    product_description: str
    contact_first_name: str
    has_mobile_app: bool


NATURAL_WRITING_GUIDE = """
Goal: give a founder a reason to reply — not prove you scraped their website.

Write like a real person who looked at the product for 60 seconds, then emailed from
their inbox. Not ChatGPT. Not a sales sequence. Not a tech-detector report.

Required structure (keep short):
1) subject — THIS IS THE MOST IMPORTANT LINE. Make the founder curious enough to open.
   Rules for subject:
   - Unique to THIS company/product. Use a product detail, audience, or mobile angle.
   - Max ~8 words. Lowercase ok. Question or incomplete thought is good.
   - Must feel different from other cold emails; never reuse a generic pattern.
   - Good examples (STYLE ONLY — invent a fresh subject for THIS company.
     Never copy these example brands or phrases literally):
     "<TheirProduct> outside the browser?"
     "<TheirProduct> on iPhone yet?"
     "<TheirProduct> without the nagging emails?"
     "native app for <TheirProduct>?"
     "saw <TheirProduct> — pocket version?"
   - Never reuse leftover example brands (Univex, Dojo, Pesterly, Zephyrax, etc.)
     unless that exact brand is the company you are writing to.
   - Hard ban these subject patterns (never use):
     "quick thought on …"
     "idea for …"
     "Inquiry About …"
     "Exploring … Opportunities"
     "Flutter for …" / "Mobile idea for …"
     anything that is just "quick thought on {company}"
     the literal string "Univex outside the browser?"
2) opening — If a real first name is provided, write it literally, e.g. "Hi Priya,".
   If no real first name is provided, skip the greeting and start the body.
   Never invent names. Never write "Hi there,". Never write placeholders like
   "{{first_name}}" or "{{name}}" — those are forbidden.
3) body — 2–3 short sentences ONLY:
   a) One sentence showing you understand what they build (use product description).
   b) One curious question/observation about mobile (ask if it's on the roadmap —
      do NOT claim they "need" an app or that mobile will "improve engagement").
   c) One concrete sentence about what YOU do: Flutter mobile apps for early-stage teams,
      so their web team can stay focused on the product.
4) cta — one soft question (roadmap / timing), not "next steps for a partnership".
5) signature must be exactly "{{sender_name}}" (this is the ONLY allowed placeholder)

Hard bans (never write these):
- Literal template tokens: "{{first_name}}", "{{name}}", "{{company}}", "{{anything}}"
  except signature which must be exactly "{{sender_name}}"
- Listing their tech stack (frameworks, hosting, analytics tools, etc.)
- "Detected stack", "modern SaaS", "technical partnership", "accelerate product delivery"
- "I hope this email finds you well", "Greetings from …", "synergy", "leverage", "utilize"
- "Would X be open to a short conversation about next steps for Y"
- Assuming they need mobile; telling them they have a "mobile opportunity"
- Bullet lists, markdown, emojis, exclamation overload

Facts:
- Use only the company facts provided.
- Do not invent contacts, technologies, websites, or Flutter/Dart evidence.
- If Flutter/Dart evidence is "no", do not claim they already use Flutter/Dart.
- Technologies below are INTERNAL CONTEXT ONLY — never mention them in the email.
""".strip()

EMAIL_JSON_SCHEMA = """
Return ONLY a JSON object with exactly these keys (plain JSON, no markdown fences):
{"subject":"string","opening":"string","body":"string","cta":"string","signature":"{{sender_name}}"}
Keep each value concise and human-sounding. Do not include explanations or extra keys.
""".strip()

FOLLOWUP_JSON_SCHEMA = EMAIL_JSON_SCHEMA

DEFAULT_EMAIL_REQUIRED_FIELDS: tuple[str, ...] = ("subject", "opening", "body", "cta")
SUBJECT_ONLY_REQUIRED_FIELDS: tuple[str, ...] = ("subject",)


def _contacts_summary(contacts: ContactDiscoveryReport | None) -> str:
    if contacts is None or not contacts.contacts:
        if contacts and contacts.emails:
            return f"Emails found: {', '.join(contacts.emails[:3])}"
        return "No contacts discovered"
    lines: list[str] = []
    for contact in contacts.contacts[:5]:
        name = normalize_person_name(contact.full_name) or normalize_person_name(contact.first_name)
        if not name:
            continue
        parts = [name]
        if contact.role:
            parts.append(f"({contact.role})")
        if contact.email:
            parts.append(f"<{contact.email}>")
        lines.append(" ".join(parts))
    if lines:
        return "; ".join(lines)
    if contacts and contacts.emails:
        return f"Emails found: {', '.join(contacts.emails[:3])}"
    return "No contacts discovered"


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


def _product_description(lead: CompleteLead, personalized: PersonalizedEmailContext) -> str:
    profile: CompanyProfile | None = lead.company_profile
    for value in (
        profile.short_description if profile else None,
        lead.startup.description,
        lead.website_profile.description if lead.website_profile else None,
        personalized.company_summary,
    ):
        text = (value or "").strip()
        if text:
            return text
    return "Product description unavailable"


def _contact_first_name(lead: CompleteLead) -> str:
    candidates: list[str] = []
    if lead.lead_intelligence and lead.lead_intelligence.best_contact:
        contact = lead.lead_intelligence.best_contact
        if contact.first_name:
            candidates.append(contact.first_name)
        if contact.full_name:
            candidates.append(contact.full_name)
    if lead.contacts and lead.contacts.contacts:
        for contact in lead.contacts.contacts:
            if contact.first_name:
                candidates.append(contact.first_name)
            if contact.full_name:
                candidates.append(contact.full_name)
    for raw in candidates:
        cleaned = normalize_person_name(raw)
        if cleaned:
            return cleaned
    return ""


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
        product_description=_product_description(lead, personalized),
        contact_first_name=_contact_first_name(lead),
        has_mobile_app=bool(personalized.has_mobile_app),
    )


def build_email_prompt(context: EmailPromptContext) -> str:
    return _format_prompt(
        task=(
            "Write one cold email that makes a founder think: "
            "'this person noticed something interesting about my product.' "
            "Not: 'this person scanned my website and wants to sell development.'\n\n"
            f"{NATURAL_WRITING_GUIDE}"
        ),
        context=context,
        schema=EMAIL_JSON_SCHEMA,
    )


def build_subject_prompt(context: EmailPromptContext) -> str:
    return _format_prompt(
        task=(
            "Write ONLY a unique, founder-attracting email subject (max 8 words). "
            "Anchor it in this company's product or a playful mobile angle. "
            "Never use 'quick thought on …' or any other generic template.\n\n"
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
    return _format_prompt(
        task=(
            f"Write a short, human follow-up sent {days_since_sent} days after "
            f'the original email with subject "{previous_subject}". '
            "Bump once + ask if mobile is still off the roadmap. No guilt trips. "
            "Subject must be a fresh follow-up line — not 'quick thought on …'.\n\n"
            f"{NATURAL_WRITING_GUIDE}"
        ),
        context=context,
        schema=FOLLOWUP_JSON_SCHEMA,
    )


_BANNED_SUBJECT_PREFIXES = (
    "quick thought on",
    "idea for",
    "inquiry about",
    "exploring ",
    "mobile idea for",
    "flutter for",
    "flutter idea for",
)

# Brands that only appeared as prompt examples — never allow them for other companies.
_PROMPT_EXAMPLE_BRANDS = frozenset(
    {
        "univex",
        "dojo",
        "pesterly",
        "zephyrax",
        "monster battle arena",
    }
)


def is_generic_subject(subject: str | None) -> bool:
    text = re.sub(r"\s+", " ", (subject or "").strip().lower())
    if not text:
        return True
    return any(text.startswith(prefix) for prefix in _BANNED_SUBJECT_PREFIXES)


def subject_uses_wrong_example_brand(subject: str | None, company_name: str | None) -> bool:
    """True when Ollama copied a prompt-example brand into another company's subject."""
    text = re.sub(r"\s+", " ", (subject or "").strip().lower())
    if not text:
        return False
    company = re.sub(r"\s+", " ", (company_name or "").strip().lower())
    for brand in _PROMPT_EXAMPLE_BRANDS:
        if brand in text and brand not in company:
            return True
    return False


def should_replace_subject(subject: str | None, company_name: str | None) -> bool:
    return is_generic_subject(subject) or subject_uses_wrong_example_brand(subject, company_name)


def _product_keyword(product_description: str, company_name: str) -> str:
    """Pull a short human phrase from the product description for subjects."""
    text = re.sub(r"\s+", " ", (product_description or "").strip())
    if not text:
        return ""
    for sep in (". ", "! ", "? ", " — ", " - "):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
            break
    # Drop leading "Company is/are ..." fluff.
    lowered = text.lower()
    company_l = (company_name or "").strip().lower()
    for prefix in (
        f"{company_l} is ",
        f"{company_l} are ",
        f"{company_l} — ",
        f"{company_l} - ",
        "we are ",
        "we're ",
    ):
        if prefix and lowered.startswith(prefix):
            text = text[len(prefix) :].strip()
            lowered = text.lower()
            break
    words = text.split()
    if len(words) > 5:
        text = " ".join(words[:5]).rstrip(",;:")
    return text.strip(" .")


def build_fallback_subject(
    *,
    company_name: str,
    product_description: str = "",
    has_mobile_app: bool = False,
) -> str:
    """Varied, product-aware subjects when Ollama is unavailable."""
    company = (company_name or "").strip() or "your product"
    hook = _product_keyword(product_description, company)

    candidates: list[str]
    if has_mobile_app:
        candidates = [
            f"{company} mobile — next step?",
            f"noticed {company}'s app",
            f"{company} beyond the current app?",
            f"flutter angle for {company}?",
        ]
        if hook:
            candidates.extend(
                [
                    f"{hook} — on more devices?",
                    f"saw {company}: {hook}?",
                ]
            )
    else:
        candidates = [
            f"{company} on mobile?",
            f"{company} outside the browser?",
            f"pocket version of {company}?",
            f"noticed {company} — mobile yet?",
            f"native app for {company}?",
            f"{company} on iPhone yet?",
        ]
        if hook:
            candidates.extend(
                [
                    f"{hook} — mobile?",
                    f"{company}: {hook} on phone?",
                    f"saw {hook} — app yet?",
                ]
            )

    # Stable per company so regenerations don't bounce randomly, but different
    # companies land on different patterns.
    index = abs(hash(company.lower())) % len(candidates)
    subject = candidates[index].strip()
    # Keep subjects short for inbox scan.
    words = subject.split()
    if len(words) > 9:
        subject = " ".join(words[:9])
    return subject


def _format_prompt(*, task: str, context: EmailPromptContext, schema: str) -> str:
    industry = context.industry or "Unknown"
    category = context.category or "Unknown"
    website = context.company_website or "Unknown"
    flutter_evidence = "yes" if context.is_flutter_lead else "no"
    mobile_found = "yes" if context.has_mobile_app else "no"
    first_name = context.contact_first_name or "(none — do not invent a name)"
    # Keep stack as internal-only context; models often copy if labeled "Technologies".
    internal_stack = (
        ", ".join(context.technologies) if context.technologies else "none detected"
    )

    return f"""
{task}

Facts (rewrite in your own words — do not paste template phrases):

Company brand name: {context.company_name}
Website: {website}
What they build (use this): {context.product_description}
Industry/category: {industry} / {category}
Native mobile app found: {mobile_found}
Mobile note: {context.mobile_opportunity}
Flutter/Dart evidence: {flutter_evidence}
Contact first name (only if real): {first_name}
Known contacts: {context.contacts_summary}
Your concrete offer: Flutter mobile apps for early-stage teams without adding a full-time engineer

INTERNAL ONLY — never mention in subject/opening/body/cta:
Stack signals: {internal_stack}
Lead score: {context.lead_score:.1f}

{schema}
""".strip()


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
