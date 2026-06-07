"""Authenticated nav chrome: avatar bubble and display name."""
from sqlalchemy.orm import Session

from app.services import onboarding_service
from app.utils.profile_labels import format_user_badge


def nav_user(db: Session, account_id: int | None) -> dict:
    if not account_id:
        return {}
    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    return {
        "nav_display_name": user.display_name or "Your profile",
        "nav_avatar_url": "/onboarding/media/avatar" if user.avatar_path else None,
        "nav_user_badge": format_user_badge(
            gender=user.gender,
            preferred_genders=user.preferred_genders,
            goals=user.intentions,
        ),
    }