from urllib.parse import urlparse


def normalize_website(url: str) -> str:
    cleaned = url.strip()
    if not cleaned:
        return cleaned

    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"

    parsed = urlparse(cleaned)
    host = parsed.netloc or parsed.path.split("/")[0]
    host = host.lower()

    if host.startswith("www."):
        host = host[4:]

    return host.rstrip("/")


def _hostname(url: str) -> str:
    cleaned = url.strip()
    if not cleaned:
        return ""
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    parsed = urlparse(cleaned)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def is_producthunt_host(url: str) -> bool:
    host = _hostname(url)
    return host == "producthunt.com" or host.endswith(".producthunt.com")


def is_producthunt_redirect(url: str) -> bool:
    cleaned = url.strip()
    if not cleaned:
        return False
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    parsed = urlparse(cleaned)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host != "producthunt.com" and not host.endswith(".producthunt.com"):
        return False
    return parsed.path.startswith("/r/")


def is_intermediate_or_cdn_host(url: str) -> bool:
    """True for Cloudflare/CDN/challenge hosts that are not company sites."""
    host = _hostname(url)
    if not host:
        return False
    if host == "cloudflare.com" or host.endswith(".cloudflare.com"):
        return True
    if host.endswith(".cloudflareinsights.com") or host.endswith(".cf-ipfs.com"):
        return True
    path = urlparse(
        url if url.startswith(("http://", "https://")) else f"https://{url}"
    ).path.lower()
    return "/cdn-cgi/" in path


def is_blog_host(url: str) -> bool:
    """True when the host itself is a blog subdomain (not a company homepage)."""
    host = _hostname(url)
    if not host:
        return False
    return host.startswith("blog.") or host.startswith("blogs.")


def is_usable_company_website(url: str) -> bool:
    """False for Product Hunt redirects/hosts, CDN intermediates, and bare blog hosts."""
    cleaned = url.strip()
    if not cleaned:
        return False
    if is_producthunt_redirect(cleaned) or is_producthunt_host(cleaned):
        return False
    if is_intermediate_or_cdn_host(cleaned):
        return False
    if is_blog_host(cleaned):
        return False
    return bool(_hostname(cleaned))


def website_identity(url: str) -> str:
    """Dedup key: domain for normal sites, unique /r/ path for Product Hunt redirects."""
    cleaned = url.strip()
    if not cleaned:
        return ""
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    if is_producthunt_redirect(cleaned):
        parsed = urlparse(cleaned)
        path = parsed.path.rstrip("/").lower()
        return f"producthunt.com{path}"
    return normalize_website(cleaned)


def canonical_lead_website(url: str) -> str:
    """Store full Product Hunt /r/ URLs; otherwise store the normalized domain."""
    cleaned = url.strip()
    if not cleaned:
        return cleaned
    if is_producthunt_redirect(cleaned):
        parsed = urlparse(
            cleaned if cleaned.startswith(("http://", "https://")) else f"https://{cleaned}"
        )
        return f"https://www.producthunt.com{parsed.path.rstrip('/')}"
    return normalize_website(cleaned)
