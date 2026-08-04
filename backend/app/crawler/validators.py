from app.crawler.types import DownloadResult, WebsiteProfile


def validate_download(download: DownloadResult | None) -> list[str]:
    errors: list[str] = []
    if download is None:
        return ["HTML download failed"]
    if not download.html.strip():
        errors.append("HTML content is empty")
    if download.status_code < 200 or download.status_code >= 400:
        errors.append(f"Invalid status code: {download.status_code}")
    if not download.final_url.strip():
        errors.append("Final URL is missing")
    return errors


def validate_profile(profile: WebsiteProfile) -> list[str]:
    errors: list[str] = []
    if not profile.url.strip():
        errors.append("URL is missing")
    if not profile.final_url.strip():
        errors.append("Final URL is missing")
    if not profile.title or not profile.title.strip():
        errors.append("Title is missing")
    if profile.status_code is None:
        errors.append("Status code is missing")
    elif profile.status_code < 200 or profile.status_code >= 400:
        errors.append(f"Invalid status code: {profile.status_code}")
    return errors
