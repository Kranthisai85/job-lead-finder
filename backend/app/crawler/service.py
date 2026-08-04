from app.core.logger import get_logger
from app.crawler.base import BaseCrawler, HttpWebsiteCrawler
from app.crawler.types import WebsiteProfile


class WebsiteCrawlerService:
    def __init__(self, crawler: BaseCrawler | None = None) -> None:
        self.crawler = crawler or HttpWebsiteCrawler()
        self.logger = get_logger(__name__)

    async def analyze(self, url: str) -> WebsiteProfile:
        self.logger.info("service=WebsiteCrawlerService action=analyze url=%s", url)
        profile = await self.crawler.run(url)
        self.logger.info(
            "service=WebsiteCrawlerService action=completed url=%s valid=%s title=%s",
            url,
            profile.valid,
            profile.title,
        )
        return profile
