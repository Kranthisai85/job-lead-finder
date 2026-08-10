"""Outbound sender identity used in email signatures."""

from __future__ import annotations

from pymongo import IndexModel

from app.models.base import BaseDocument

DEFAULT_SENDER_PROFILE_KEY = "default"


class SenderProfileDocument(BaseDocument):
    """Singleton-style profile (one row with key=default)."""

    profile_key: str = DEFAULT_SENDER_PROFILE_KEY
    display_name: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    phone_number: str = ""

    class Settings:
        name = "sender_profiles"
        indexes = [
            IndexModel([("profile_key", 1)], unique=True),
        ]
