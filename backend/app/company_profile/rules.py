from __future__ import annotations

from dataclasses import dataclass

from app.company_profile.types import (
    BusinessCategory,
    PricingModel,
    ProductType,
    TargetAudience,
)


@dataclass(frozen=True)
class KeywordRule:
    label: str
    keywords: tuple[str, ...]
    weight: int = 1


CATEGORY_RULES: tuple[KeywordRule, ...] = (
    KeywordRule("Developer Tools", ("developer tools", "devtools", "for developers", "sdk", "ide")),
    KeywordRule("Healthcare", ("healthcare", "healthtech", "medical", "patient", "clinic")),
    KeywordRule("Fintech", ("fintech", "banking", "finance", "lending", "wealth")),
    KeywordRule("EdTech", ("edtech", "education", "learning", "classroom", "course")),
    KeywordRule("HR", ("human resources", "hr software", "recruiting", "payroll", "talent")),
    KeywordRule("Marketing", ("marketing", "campaign", "seo", "growth", "ads")),
    KeywordRule("CRM", ("crm", "customer relationship", "pipeline", "salesforce")),
    KeywordRule("Cybersecurity", ("security", "cyber", "threat", "vulnerability", "identity")),
    KeywordRule(
        "AI", ("artificial intelligence", "machine learning", "llm", "generative ai", " ai ")
    ),
    KeywordRule("Analytics", ("analytics", "metrics", "telemetry", "insights", "data platform")),
    KeywordRule("Productivity", ("productivity", "workflow", "collaboration", "task", "notes")),
    KeywordRule("Legal", ("legal", "law", "compliance", "contract", "attorney")),
    KeywordRule("E-commerce", ("ecommerce", "e-commerce", "shopify", "storefront", "retail")),
    KeywordRule("Payments", ("payments", "checkout", "billing", "invoicing", "stripe")),
    KeywordRule("DevOps", ("devops", "ci/cd", "deployment", "kubernetes", "observability")),
    KeywordRule("Infrastructure", ("infrastructure", "cloud", "hosting", "serverless", "cdn")),
    KeywordRule("Open Source", ("open source", "opensource", "oss", "github.com")),
    KeywordRule("Communication", ("messaging", "chat", "communication", "video calls", "meetings")),
)

INDUSTRY_RULES: tuple[KeywordRule, ...] = (
    KeywordRule(
        "Project Management", ("issue tracking", "project management", "roadmap", "sprints")
    ),
    KeywordRule("Scheduling", ("scheduling", "calendar", "booking", "appointments")),
    KeywordRule("Identity", ("authentication", "identity", "sso", "login")),
    KeywordRule("Databases", ("database", "postgres", "sql", "storage")),
    KeywordRule("Email", ("email api", "transactional email", "newsletter")),
    KeywordRule("Design", ("design", "prototyping", "figma", "ui kit")),
    KeywordRule("Video", ("video", "recording", "streaming")),
    KeywordRule("Commerce", ("payments", "checkout", "subscriptions")),
)

PRODUCT_TYPE_RULES: tuple[KeywordRule, ...] = (
    KeywordRule("API", ("api", "rest api", "graphql", "sdk")),
    KeywordRule("Marketplace", ("marketplace", "two-sided", "buyers and sellers")),
    KeywordRule("Browser Extension", ("browser extension", "chrome extension", "firefox add")),
    KeywordRule("Desktop App", ("desktop app", "mac app", "windows app", "electron")),
    KeywordRule("Mobile App", ("mobile app", "ios app", "android app", "app store")),
    KeywordRule("Platform", ("platform", "ecosystem", "integrations")),
    KeywordRule("Consulting", ("consulting", "agency services", "professional services")),
    KeywordRule("SaaS", ("saas", "software as a service", "cloud software", "subscription")),
)

AUDIENCE_RULES: tuple[KeywordRule, ...] = (
    KeywordRule("Developers", ("developers", "engineers", "software teams", "devops")),
    KeywordRule("Designers", ("designers", "design teams", "product designers")),
    KeywordRule("Sales Teams", ("sales teams", "revenue teams", "account executives")),
    KeywordRule("HR Teams", ("hr teams", "people ops", "recruiters")),
    KeywordRule("Students", ("students", "learners", "campus")),
    KeywordRule("Teachers", ("teachers", "educators", "instructors")),
    KeywordRule("Startups", ("startups", "founders", "early-stage")),
    KeywordRule("Enterprises", ("enterprise", "enterprises", "large organizations")),
    KeywordRule("SMBs", ("smb", "small business", "small businesses")),
    KeywordRule("Agencies", ("agencies", "agency", "clients")),
)

PRICING_RULES: tuple[KeywordRule, ...] = (
    KeywordRule("Freemium", ("freemium", "free plan", "free forever", "start free", "try free")),
    KeywordRule("Free", ("100% free", "completely free", "free and open")),
    KeywordRule(
        "Custom Pricing", ("custom pricing", "contact sales", "talk to sales", "get a quote")
    ),
    KeywordRule("Enterprise", ("enterprise plan", "enterprise pricing", "for enterprise")),
    KeywordRule("Paid", ("pricing", "paid plan", "pro plan", "premium", "$")),
)


def _score_rules(corpus: str, rules: tuple[KeywordRule, ...]) -> list[tuple[str, int, list[str]]]:
    scored: list[tuple[str, int, list[str]]] = []
    for rule in rules:
        hits = [keyword for keyword in rule.keywords if keyword in corpus]
        if hits:
            scored.append((rule.label, len(hits) * rule.weight, hits))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


def infer_business_category(corpus: str) -> tuple[BusinessCategory | None, list[str]]:
    scored = _score_rules(corpus, CATEGORY_RULES)
    if not scored:
        return None, []
    label, _, hits = scored[0]
    return label, [f"category:{label}:{hit}" for hit in hits]  # type: ignore[return-value]


def infer_industry(corpus: str) -> tuple[str | None, list[str]]:
    scored = _score_rules(corpus, INDUSTRY_RULES)
    if not scored:
        return None, []
    label, _, hits = scored[0]
    return label, [f"industry:{label}:{hit}" for hit in hits]


def infer_product_type(corpus: str) -> tuple[ProductType | None, list[str]]:
    scored = _score_rules(corpus, PRODUCT_TYPE_RULES)
    if not scored:
        return "SaaS", ["product_type:SaaS:default"]
    label, _, hits = scored[0]
    return label, [f"product_type:{label}:{hit}" for hit in hits]  # type: ignore[return-value]


def infer_target_audience(corpus: str) -> tuple[TargetAudience | None, list[str]]:
    scored = _score_rules(corpus, AUDIENCE_RULES)
    if not scored:
        return None, []
    label, _, hits = scored[0]
    return label, [f"audience:{label}:{hit}" for hit in hits]  # type: ignore[return-value]


def infer_pricing_model(
    corpus: str, *, has_pricing_page: bool
) -> tuple[PricingModel | None, list[str]]:
    scored = _score_rules(corpus, PRICING_RULES)
    if scored:
        label, _, hits = scored[0]
        return label, [f"pricing:{label}:{hit}" for hit in hits]  # type: ignore[return-value]
    if has_pricing_page:
        return "Paid", ["pricing:Paid:pricing_page"]
    return None, []
