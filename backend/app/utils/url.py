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
