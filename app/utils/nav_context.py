"""Authenticated nav chrome: avatar bubble and display name."""
from pathlib import Path

from sqlalchemy.orm import Session

from app.services import onboarding_service
from app.utils.profile_labels import format_user_badge


def _avatar_media_url(path_str: str | None) -> str | None:
    if not path_str:
        return None
    path = Path(path_str)
    if not path.is_file():
        return None
    version = int(path.stat().st_mtime)
    return f"/onboarding/media/avatar?v={version}"


def nav_user(db: Session, account_id: int | None) -> dict:
    if not account_id:
        return {}
    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    display = (user.display_name or "").strip() or "Your profile"
    initial = display[0].upper() if display else "U"
    return {
        "nav_display_name": display,
        "nav_avatar_initial": initial,
        "nav_avatar_url": _avatar_media_url(user.avatar_path),
        "nav_user_badge": format_user_badge(
            gender=user.gender,
            preferred_genders=user.preferred_genders,
            goals=user.intentions,
        ),
    }