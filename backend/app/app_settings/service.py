from __future__ import annotations

from app.app_settings.types import AppSettings, AppSettingsUpdate
from app.core.config import settings
from app.models.app_settings import DEFAULT_APP_SETTINGS_KEY, AppSettingsDocument


class AppSettingsService:
    """Load/save dashboard app settings (singleton)."""

    def _to_settings(self, doc: AppSettingsDocument | None) -> AppSettings:
        if doc is None:
            return AppSettings(
                scheduler_timezone=settings.scheduler_timezone,
            )
        return AppSettings(
            skip_duplicate_companies=bool(doc.skip_duplicate_companies),
            scheduler_hour=int(getattr(doc, "scheduler_hour", 9)),
            scheduler_minute=int(getattr(doc, "scheduler_minute", 0)),
            scheduler_timezone=settings.scheduler_timezone,
        )

    async def get_settings(self) -> AppSettings:
        doc = await AppSettingsDocument.find_one(
            AppSettingsDocument.settings_key == DEFAULT_APP_SETTINGS_KEY
        )
        return self._to_settings(doc)

    async def update_settings(self, payload: AppSettingsUpdate) -> AppSettings:
        doc = await AppSettingsDocument.find_one(
            AppSettingsDocument.settings_key == DEFAULT_APP_SETTINGS_KEY
        )
        if doc is None:
            doc = AppSettingsDocument(
                settings_key=DEFAULT_APP_SETTINGS_KEY,
                skip_duplicate_companies=payload.skip_duplicate_companies,
                scheduler_hour=payload.scheduler_hour,
                scheduler_minute=payload.scheduler_minute,
            )
            await doc.insert()
        else:
            doc.skip_duplicate_companies = payload.skip_duplicate_companies
            doc.scheduler_hour = payload.scheduler_hour
            doc.scheduler_minute = payload.scheduler_minute
            await doc.save()
        return self._to_settings(doc)
