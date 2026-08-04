import re
from collections.abc import Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from app.crawler.types import LinkClassification, SocialLinks

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_PATTERN = re.compile(
    r"(?:\+?\d{1,3}[\s\-.]?)?(?:\(?\d{2,4}\)?[\s\-.]?)?\d{3,4}[\s\-.]?\d{3,4}"
)

SOCIAL_DOMAINS: dict[str, tuple[str, ...]] = {
    "linkedin": ("linkedin.com",),
    "twitter": ("twitter.com", "x.com"),
    "github": ("github.com",),
    "facebook": ("facebook.com", "fb.com"),
    "instagram": ("instagram.com",),
    "youtube": ("youtube.com", "youtu.be"),
    "discord": ("discord.com", "discord.gg"),
    "medium": ("medium.com",),
}

SPECIAL_PAGE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "contact_pages": ("contact", "support", "get-in-touch", "reach-us"),
    "about_pages": ("about", "company", "team", "who-we-are"),
    "career_pages": ("career", "careers", "join-us", "work-with-us"),
    "jobs_pages": ("jobs", "job-openings", "openings", "hiring"),
    "pricing_pages": ("pricing", "plans", "plan", "buy"),
    "blog_pages": ("blog", "news", "articles", "posts"),
    "documentation_pages": ("docs", "documentation", "help", "guide", "guides"),
    "api_pages": ("api", "developers", "developer", "reference"),
}


def extract_title(soup: BeautifulSoup) -> str | None:
    if soup.title and soup.title.string:
        title = str(soup.title.string).strip()
        if title:
            return title

    og_title = soup.find("meta", property="og:title")
    if isinstance(og_title, Tag):
        content = og_title.get("content")
        if content:
            return str(content).strip()
    return None


def extract_meta_description(soup: BeautifulSoup) -> str | None:
    meta = soup.find("meta", attrs={"name": "description"})
    if isinstance(meta, Tag) and meta.get("content"):
        return str(meta.get("content")).strip()

    og_description = soup.find("meta", property="og:description")
    if isinstance(og_description, Tag) and og_description.get("content"):
        return str(og_description.get("content")).strip()
    return None


def extract_canonical_url(soup: BeautifulSoup, base_url: str) -> str | None:
    canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
    if isinstance(canonical, Tag) and canonical.get("href"):
        return urljoin(base_url, str(canonical.get("href")).strip())
    return None


def extract_favicon(soup: BeautifulSoup, base_url: str) -> str | None:
    icon = soup.find("link", rel=lambda value: value and "icon" in str(value).lower())
    if isinstance(icon, Tag) and icon.get("href"):
        return urljoin(base_url, str(icon.get("href")).strip())
    return urljoin(base_url, "/favicon.ico")


def extract_open_graph_tags(soup: BeautifulSoup) -> dict[str, str]:
    tags: dict[str, str] = {}
    for meta in soup.find_all("meta", property=True):
        if not isinstance(meta, Tag):
            continue
        property_name = str(meta.get("property", ""))
        content = meta.get("content")
        if property_name.startswith("og:") and content:
            tags[property_name] = str(content).strip()
    return tags


def extract_twitter_tags(soup: BeautifulSoup) -> dict[str, str]:
    tags: dict[str, str] = {}
    for meta in soup.find_all("meta", attrs={"name": True}):
        if not isinstance(meta, Tag):
            continue
        name = str(meta.get("name", ""))
        content = meta.get("content")
        if name.startswith("twitter:") and content:
            tags[name] = str(content).strip()
    return tags


def extract_language(soup: BeautifulSoup) -> str | None:
    html_tag = soup.find("html")
    if isinstance(html_tag, Tag) and html_tag.get("lang"):
        return str(html_tag.get("lang")).strip()
    return None


def _normalize_href(href: str, base_url: str) -> str | None:
    cleaned = href.strip()
    if not cleaned or cleaned.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    return urljoin(base_url, cleaned)


def extract_links(soup: BeautifulSoup, base_url: str) -> tuple[list[str], list[str]]:
    base_host = urlparse(base_url).netloc.lower()
    internal: list[str] = []
    external: list[str] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        absolute = _normalize_href(str(anchor.get("href")), base_url)
        if absolute is None or absolute in seen:
            continue
        seen.add(absolute)
        host = urlparse(absolute).netloc.lower()
        if host == base_host:
            internal.append(absolute)
        else:
            external.append(absolute)

    return internal, external


def extract_social_links(links: Iterable[str]) -> SocialLinks:
    buckets: dict[str, list[str]] = {key: [] for key in SOCIAL_DOMAINS}
    for link in links:
        host = urlparse(link).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        for network, domains in SOCIAL_DOMAINS.items():
            if any(host == domain or host.endswith(f".{domain}") for domain in domains):
                if link not in buckets[network]:
                    buckets[network].append(link)
                break
    return SocialLinks(**buckets)


def extract_emails(text: str, soup: BeautifulSoup) -> list[str]:
    emails = set(EMAIL_PATTERN.findall(text))
    for mailto in soup.select('a[href^="mailto:"]'):
        href = str(mailto.get("href", ""))
        address = href.replace("mailto:", "").split("?")[0].strip()
        if address:
            emails.add(address)
    return sorted(emails)


def extract_phones(text: str, soup: BeautifulSoup) -> list[str]:
    phones = set()
    for match in PHONE_PATTERN.findall(text):
        digits = re.sub(r"\D", "", match)
        if 7 <= len(digits) <= 15:
            phones.add(match.strip())
    for tel in soup.select('a[href^="tel:"]'):
        href = str(tel.get("href", ""))
        number = href.replace("tel:", "").strip()
        if number:
            phones.add(number)
    return sorted(phones)


def classify_special_pages(links: Iterable[str]) -> LinkClassification:
    classified: dict[str, list[str]] = {key: [] for key in SPECIAL_PAGE_KEYWORDS}
    for link in links:
        path = urlparse(link).path.lower()
        for category, keywords in SPECIAL_PAGE_KEYWORDS.items():
            if any(keyword in path for keyword in keywords):
                if link not in classified[category]:
                    classified[category].append(link)
    return LinkClassification(**classified)


def extract_app_store_links(links: Iterable[str]) -> list[str]:
    return sorted(
        {link for link in links if "apps.apple.com" in link or "itunes.apple.com" in link}
    )


def extract_play_store_links(links: Iterable[str]) -> list[str]:
    return sorted({link for link in links if "play.google.com" in link})


def detect_technologies(soup: BeautifulSoup, headers: dict[str, str]) -> list[str]:
    technologies: list[str] = []
    generator = soup.find("meta", attrs={"name": "generator"})
    if isinstance(generator, Tag) and generator.get("content"):
        technologies.append(str(generator.get("content")).strip())

    server = headers.get("server") or headers.get("Server")
    if server:
        technologies.append(str(server).strip())

    powered_by = headers.get("x-powered-by") or headers.get("X-Powered-By")
    if powered_by:
        technologies.append(str(powered_by).strip())

    return sorted(set(technologies))
