"""Keyword rules and HTML/corpus extractors for company intelligence."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from app.company_intelligence.models import (
    BUSINESS_MODELS,
    COMPANY_STAGES,
    PRICING_MODELS,
    TARGET_CUSTOMERS,
)

PAGE_PATHS: tuple[str, ...] = (
    "/about",
    "/about-us",
    "/company",
    "/pricing",
    "/plans",
    "/features",
    "/product",
    "/products",
    "/solutions",
    "/faq",
    "/faqs",
)

MAX_EXTRA_PAGES = 5
PAGE_TIMEOUT_S = 8.0

BUSINESS_MODEL_RULES: dict[str, tuple[str, ...]] = {
    "SaaS": ("saas", "software as a service", "cloud software", "subscription software"),
    "Marketplace": ("marketplace", "two-sided", "buyers and sellers", "multi-vendor"),
    "Agency": ("agency", "consulting firm", "client projects", "professional services"),
    "Developer Tool": (
        "developer tools",
        "devtools",
        "for developers",
        "sdk",
        "api platform",
        "cli tool",
    ),
    "Ecommerce": ("ecommerce", "e-commerce", "online store", "shopify", "storefront"),
    "Open Source": ("open source", "opensource", "oss ", "github.com/", "mit license"),
    "AI Platform": (
        "ai platform",
        "artificial intelligence",
        "machine learning",
        "generative ai",
        "llm",
    ),
    "Enterprise Software": (
        "enterprise software",
        "for enterprise",
        "enterprise platform",
        "fortune 500",
    ),
    "Consumer App": ("consumer app", "for consumers", "personal use", "mobile app for everyone"),
    "FinTech": ("fintech", "financial technology", "banking", "payments platform", "lending"),
    "Healthcare": ("healthcare", "healthtech", "medical", "patient care", "clinical"),
    "EdTech": ("edtech", "education technology", "online learning", "classroom", "for students"),
}

TARGET_CUSTOMER_RULES: dict[str, tuple[str, ...]] = {
    "B2B": ("b2b", "business-to-business", "for businesses", "for companies", "business customers"),
    "B2C": ("b2c", "business-to-consumer", "for consumers", "for individuals", "personal"),
    "Enterprise": ("enterprise", "large organizations", "fortune 500", "global companies"),
    "SMB": ("smb", "small business", "small businesses", "mid-market"),
    "Startup": ("startups", "for startups", "founders", "early-stage companies"),
    "Developers": ("developers", "software engineers", "engineering teams", "devops"),
    "Creators": ("creators", "content creators", "influencers", "creators economy"),
    "Students": ("students", "learners", "campus", "universities"),
}

PRICING_RULES: dict[str, tuple[str, ...]] = {
    "Freemium": ("freemium", "free plan", "free forever", "start free", "try free"),
    "Free": ("100% free", "completely free", "free and open", "no cost"),
    "Subscription": ("subscription", "monthly plan", "per month", "/mo", "billed annually"),
    "Enterprise": ("enterprise plan", "enterprise pricing", "contact sales", "custom pricing"),
    "Paid": ("paid plan", "pro plan", "premium plan", "pricing starts", "$"),
}

STAGE_RULES: dict[str, tuple[str, ...]] = {
    "Idea": ("coming soon", "join waitlist", "launching soon", "idea stage"),
    "MVP": ("mvp", "beta", "early access", "private beta"),
    "Early Startup": ("seed", "pre-seed", "early-stage", "just launched", "founded in 202"),
    "Growth": ("series a", "series b", "growing team", "scaling fast", "thousands of"),
    "Scale-up": ("series c", "series d", "hypergrowth", "global expansion"),
    "Enterprise": ("public company", "ipo", "fortune 500", "enterprise-grade at scale"),
}

FUNDING_RULES: dict[str, tuple[str, ...]] = {
    "Bootstrapped": ("bootstrapped", "self-funded", "profitable without funding"),
    "Seed": ("seed round", "seed funding", "raised seed"),
    "Series A": ("series a",),
    "Series B": ("series b",),
    "Series C+": ("series c", "series d", "series e"),
    "Acquired": ("acquired by", "acquisition"),
}

PAIN_POINT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(too complex|complicated|overwhelming)\b", "Complexity / hard to use"),
    (r"\b(manual|spreadsheet|busywork)\b", "Manual workflows"),
    (r"\b(expensive|costly|overpriced)\b", "High cost of alternatives"),
    (r"\b(slow|latency|takes forever)\b", "Performance / speed"),
    (r"\b(fragmented|scattered|silos)\b", "Fragmented tools"),
    (r"\b(hard to (hire|find|recruit))\b", "Hiring difficulty"),
)

OPPORTUNITY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(automate|automation)\b", "Automation opportunity"),
    (r"\b(ai[- ]powered|artificial intelligence)\b", "AI-assisted workflows"),
    (r"\b(integrations?|connects? with)\b", "Integration ecosystem"),
    (r"\b(mobile|flutter|react native)\b", "Mobile product opportunity"),
    (r"\b(self[- ]serve|no[- ]code)\b", "Self-serve / no-code"),
)

COMPETITOR_HINTS = re.compile(
    r"(?:vs\.?|versus|alternative to|compared to|better than|unlike)\s+"
    r"([A-Za-z][A-Za-z0-9&.\-]*)",
    re.IGNORECASE,
)

KNOWN_COMPETITORS: tuple[str, ...] = (
    "Salesforce",
    "HubSpot",
    "Slack",
    "Notion",
    "Asana",
    "Jira",
    "Monday.com",
    "Shopify",
    "Stripe",
    "Twilio",
    "AWS",
    "Azure",
    "Google Cloud",
    "Zapier",
    "Intercom",
    "Zendesk",
    "Figma",
    "Linear",
    "Airtable",
    "Postman",
    "Insomnia",
)


def build_corpus(*parts: str | None) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip()).lower()


def score_label(corpus: str, rules: dict[str, tuple[str, ...]]) -> tuple[str | None, list[str]]:
    best_label: str | None = None
    best_score = 0
    hits: list[str] = []
    for label, keywords in rules.items():
        matched = [kw for kw in keywords if kw in corpus]
        score = len(matched)
        if score > best_score:
            best_score = score
            best_label = label
            hits = matched
    if best_label is None:
        return None, []
    return best_label, [f"{best_label}:{hit}" for hit in hits]


def extract_hero_text(soup: BeautifulSoup) -> str:
    parts: list[str] = []
    for selector in ("h1", "h2", "[class*='hero']", "[class*='banner']", "header p"):
        for node in soup.select(selector)[:5]:
            text = " ".join(node.stripped_strings)
            if text and len(text) < 300:
                parts.append(text)
    return " ".join(parts)


def extract_faq_text(soup: BeautifulSoup) -> str:
    parts: list[str] = []
    for node in soup.select(
        "[class*='faq'], [id*='faq'], details, .accordion, section[aria-label*='FAQ' i]"
    ):
        text = " ".join(node.stripped_strings)
        if text:
            parts.append(text[:800])
    return " ".join(parts)


def extract_structured_data(soup: BeautifulSoup) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        content = script.string or script.get_text()
        if not content:
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue
        for item in _walk_jsonld(payload):
            for key in ("name", "description", "industry", "slogan", "category"):
                if key in item and item[key] and key not in result:
                    result[key] = item[key]
            org = item.get("organization") or item.get("publisher")
            if isinstance(org, dict) and org.get("name") and "organization" not in result:
                result["organization"] = org.get("name")
    return result


def extract_meta_signals(soup: BeautifulSoup) -> dict[str, str]:
    meta: dict[str, str] = {}
    for tag in soup.find_all("meta"):
        if not isinstance(tag, Tag):
            continue
        name = str(tag.get("name") or tag.get("property") or "").lower()
        content = str(tag.get("content") or "").strip()
        if not name or not content:
            continue
        if name in {
            "description",
            "og:description",
            "og:title",
            "keywords",
            "og:type",
            "twitter:description",
        }:
            meta[name] = content
    return meta


def extract_competitors(text: str) -> list[str]:
    found: list[str] = []
    for match in COMPETITOR_HINTS.finditer(text):
        name = match.group(1).strip(" .,;:")
        if name.lower() in {"the", "a", "an", "our", "their", "other"}:
            continue
        if name and name not in found and len(name) > 2:
            found.append(name.title() if name.islower() else name)
    lowered = text.lower()
    for name in KNOWN_COMPETITORS:
        if name.lower() in lowered and name not in found:
            found.append(name)
    return found[:12]


def extract_pain_points(corpus: str) -> list[str]:
    points: list[str] = []
    for pattern, label in PAIN_POINT_PATTERNS:
        if re.search(pattern, corpus, re.IGNORECASE) and label not in points:
            points.append(label)
    return points


def extract_opportunities(corpus: str) -> list[str]:
    points: list[str] = []
    for pattern, label in OPPORTUNITY_PATTERNS:
        if re.search(pattern, corpus, re.IGNORECASE) and label not in points:
            points.append(label)
    return points


def extract_keywords(corpus: str, limit: int = 20) -> list[str]:
    tokens = re.findall(r"[a-z][a-z0-9\-]{2,}", corpus.lower())
    stop = {
        "the",
        "and",
        "for",
        "with",
        "your",
        "our",
        "you",
        "this",
        "that",
        "from",
        "are",
        "has",
        "have",
        "will",
        "can",
        "all",
        "into",
        "more",
        "than",
        "when",
        "what",
        "about",
        "their",
        "they",
        "http",
        "https",
        "www",
        "com",
    }
    counts: dict[str, int] = {}
    for token in tokens:
        if token in stop:
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _ in ranked[:limit]]


def extract_main_product(
    soup: BeautifulSoup, structured: dict[str, Any], title: str | None
) -> str | None:
    if structured.get("name") and isinstance(structured["name"], str):
        return structured["name"].strip()[:120]
    h1 = soup.find("h1")
    if isinstance(h1, Tag):
        text = " ".join(h1.stripped_strings).strip()
        if text:
            return text[:120]
    if title:
        return title.split("|")[0].split("-")[0].strip()[:120]
    return None


def estimate_team_size(
    corpus: str, *, hiring_jobs: int = 0, engineering_jobs: int = 0
) -> str | None:
    if re.search(r"\b(1000\+|thousands of employees|global team)\b", corpus):
        return "1000+"
    if re.search(r"\b(200[-–]500|hundreds of|large team)\b", corpus):
        return "200-500"
    if re.search(r"\b(50[-–]200|growing team of)\b", corpus) or hiring_jobs >= 8:
        return "50-200"
    if re.search(r"\b(10[-–]50|small team|lean team)\b", corpus) or engineering_jobs >= 3:
        return "10-50"
    if re.search(r"\b(1[-–]10|solo founder|two founders|tiny team)\b", corpus):
        return "1-10"
    if hiring_jobs > 0:
        return "10-50"
    return None


def estimate_maturity(stage: str | None, funding: str | None) -> str | None:
    if stage in {"Scale-up", "Enterprise"} or funding in {"Series C+", "Acquired"}:
        return "Mature"
    if stage in {"Growth"} or funding in {"Series A", "Series B"}:
        return "Growing"
    if stage in {"MVP", "Early Startup"} or funding in {"Seed", "Bootstrapped"}:
        return "Early"
    if stage == "Idea":
        return "Nascent"
    return None


def detect_funding_status(corpus: str) -> str | None:
    label, _ = score_label(corpus, FUNDING_RULES)
    return label


def detect_pricing_model(corpus: str, *, has_pricing_page: bool) -> str:
    label, _ = score_label(corpus, PRICING_RULES)
    if label:
        return label
    if has_pricing_page:
        return "Paid"
    return "Unknown"


def detect_company_stage(corpus: str, *, hiring_jobs: int = 0) -> str | None:
    label, _ = score_label(corpus, STAGE_RULES)
    if label:
        return label
    if hiring_jobs >= 5:
        return "Growth"
    if hiring_jobs >= 1:
        return "Early Startup"
    return None


def infer_industry(business_model: str | None, keywords: list[str], corpus: str) -> str | None:
    if business_model in {"FinTech", "Healthcare", "EdTech", "Ecommerce"}:
        return business_model
    if business_model == "Developer Tool":
        return "Developer Tools"
    if business_model == "AI Platform":
        return "Artificial Intelligence"
    if business_model == "Enterprise Software":
        return "Enterprise Software"
    if "fintech" in corpus or "payments" in corpus:
        return "FinTech"
    if "health" in corpus:
        return "Healthcare"
    if "education" in corpus or "learning" in corpus:
        return "EdTech"
    if keywords:
        return keywords[0].title()
    return None


def infer_subcategory(corpus: str, business_model: str | None) -> str | None:
    mapping = (
        ("crm", "CRM"),
        ("analytics", "Analytics"),
        ("devops", "DevOps"),
        ("security", "Security"),
        ("marketing", "Marketing"),
        ("hr ", "HR"),
        ("recruit", "Recruiting"),
        ("project management", "Project Management"),
        ("api", "API Platform"),
        ("mobile", "Mobile"),
        ("flutter", "Mobile / Flutter"),
    )
    for token, label in mapping:
        if token in corpus:
            return label
    if business_model:
        return business_model
    return None


def page_looks_like(url: str, *tokens: str) -> bool:
    lowered = url.lower()
    return any(token in lowered for token in tokens)


def candidate_intelligence_urls(profile_url: str, profile_links: list[str]) -> list[str]:
    parsed = urlparse(profile_url)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    urls: list[str] = []
    for path in PAGE_PATHS:
        if origin:
            urls.append(urljoin(origin + "/", path.lstrip("/")))
    for link in profile_links:
        if page_looks_like(
            link,
            "about",
            "pricing",
            "plan",
            "feature",
            "product",
            "solution",
            "faq",
            "company",
        ):
            urls.append(link)
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        key = url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(url)
    return ordered


def _walk_jsonld(payload: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        items.append(payload)
        for value in payload.values():
            items.extend(_walk_jsonld(value))
    elif isinstance(payload, list):
        for item in payload:
            items.extend(_walk_jsonld(item))
    return items


def validate_enum(value: str | None, allowed: tuple[str, ...]) -> str | None:
    if value is None:
        return None
    return value if value in allowed else None


# Re-export enum tuples for service assertions
__all__ = [
    "BUSINESS_MODELS",
    "TARGET_CUSTOMERS",
    "PRICING_MODELS",
    "COMPANY_STAGES",
    "MAX_EXTRA_PAGES",
    "PAGE_TIMEOUT_S",
    "PAGE_PATHS",
    "build_corpus",
    "score_label",
    "extract_hero_text",
    "extract_faq_text",
    "extract_structured_data",
    "extract_meta_signals",
    "extract_competitors",
    "extract_pain_points",
    "extract_opportunities",
    "extract_keywords",
    "extract_main_product",
    "estimate_team_size",
    "estimate_maturity",
    "detect_funding_status",
    "detect_pricing_model",
    "detect_company_stage",
    "infer_industry",
    "infer_subcategory",
    "candidate_intelligence_urls",
    "page_looks_like",
    "validate_enum",
    "BUSINESS_MODEL_RULES",
    "TARGET_CUSTOMER_RULES",
]
