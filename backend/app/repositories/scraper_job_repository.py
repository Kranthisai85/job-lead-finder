from app.models.scraper_job import ScraperJob
from app.repositories.base_repository import BaseRepository


class ScraperJobRepository(BaseRepository[ScraperJob]):
    def __init__(self) -> None:
        super().__init__(ScraperJob)
