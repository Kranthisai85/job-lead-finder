from __future__ import annotations

from app.app_settings.types import AppSettings, AppSettingsUpdate
from app.models.app_settings import DEFAULT_APP_SETTINGS_KEY, AppSettingsDocument


class AppSettingsService:
    """Load/save dashboard app settings (singleton)."""

    async def get_settings(self) -> AppSettings:
        doc = await AppSettingsDocument.find_one(
            AppSettingsDocument.settings_key == DEFAULT_APP_SETTINGS_KEY
        )
        if doc is None:
            return AppSettings()
        return AppSettings(
            skip_duplicate_companies=bool(doc.skip_duplicate_companies),
        )

    async def update_settings(self, payload: AppSettingsUpdate) -> AppSettings:
        doc = await AppSettingsDocument.find_one(
            AppSettingsDocument.settings_key == DEFAULT_APP_SETTINGS_KEY
        )
        if doc is None:
            doc = AppSettingsDocument(
                settings_key=DEFAULT_APP_SETTINGS_KEY,
                skip_duplicate_companies=payload.skip_duplicate_companies,
            )
            await doc.insert()
        else:
            doc.skip_duplicate_companies = payload.skip_duplicate_companies
            await doc.save()
        return AppSettings(skip_duplicate_companies=bool(doc.skip_duplicate_companies))
