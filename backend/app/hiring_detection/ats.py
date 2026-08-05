from __future__ import annotations

from urllib.parse import urlparse

from app.hiring_detection.config import ATS_PROVIDERS


def detect_ats_provider(url: str | None, html: str = "") -> str | None:
    blob = f"{url or ''}\n{html}".lower()
    for provider, hosts in ATS_PROVIDERS.items():
        for host in hosts:
            if host.lower() in blob:
                return provider
    return None


def is_ats_url(url: str) -> bool:
    return detect_ats_provider(url) is not None


def normalize_job_url(url: str, base_url: str | None = None) -> str:
    cleaned = url.strip()
    if cleaned.startswith(("http://", "https://")):
        return cleaned.split("#", 1)[0].rstrip("/")
    if base_url:
        parsed = urlparse(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
        if cleaned.startswith("/"):
            return f"{origin}{cleaned}".rstrip("/")
        return f"{origin}/{cleaned}".rstrip("/")
    return cleaned.rstrip("/")
