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
