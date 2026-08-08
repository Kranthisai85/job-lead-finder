from __future__ import annotations

from app.models.sender_profile import DEFAULT_SENDER_PROFILE_KEY, SenderProfileDocument
from app.sender_profile.types import SenderProfile, SenderProfileUpdate


class SenderProfileService:
    """Load/save the single outbound sender profile used in email signatures."""

    async def get_profile(self) -> SenderProfile:
        doc = await SenderProfileDocument.find_one(
            SenderProfileDocument.profile_key == DEFAULT_SENDER_PROFILE_KEY
        )
        if doc is None:
            return SenderProfile()
        return SenderProfile(
            display_name=doc.display_name or "",
            linkedin_url=doc.linkedin_url or "",
            github_url=doc.github_url or "",
        )

    async def update_profile(self, payload: SenderProfileUpdate) -> SenderProfile:
        doc = await SenderProfileDocument.find_one(
            SenderProfileDocument.profile_key == DEFAULT_SENDER_PROFILE_KEY
        )
        if doc is None:
            doc = SenderProfileDocument(
                profile_key=DEFAULT_SENDER_PROFILE_KEY,
                display_name=payload.display_name.strip(),
                linkedin_url=payload.linkedin_url.strip(),
                github_url=payload.github_url.strip(),
            )
            await doc.insert()
        else:
            doc.display_name = payload.display_name.strip()
            doc.linkedin_url = payload.linkedin_url.strip()
            doc.github_url = payload.github_url.strip()
            await doc.save()
        return SenderProfile(
            display_name=doc.display_name,
            linkedin_url=doc.linkedin_url,
            github_url=doc.github_url,
        )
