"""App-level settings used by outbound lead generation."""

from __future__ import annotations

from pymongo import IndexModel

from app.models.base import BaseDocument

DEFAULT_APP_SETTINGS_KEY = "default"


class AppSettingsDocument(BaseDocument):
    """Singleton settings row (key=default)."""

    settings_key: str = DEFAULT_APP_SETTINGS_KEY
    skip_duplicate_companies: bool = True

    class Settings:
        name = "app_settings"
        indexes = [
            IndexModel([("settings_key", 1)], unique=True),
        ]
