"""Legal policy version, disclaimers, and acceptance helpers."""
from datetime import datetime

from app.models.user import UserProfile

POLICIES_VERSION = "2026-06-08"

AI_DISCLAIMER = (
    "Personal safety due diligence only — AI authenticity and catfish signals are probabilistic; "
    "always verify yourself before meeting anyone. Not a background check or ground truth."
)


def policies_accepted(user: UserProfile | None) -> bool:
    if not user:
        return False
    return (
        user.policies_accepted_at is not None
        and user.policies_version == POLICIES_VERSION
    )


def append_ai_disclaimer(text: str | None) -> str:
    base = (text or "").strip()
    if not base:
        return AI_DISCLAIMER
    if AI_DISCLAIMER in base:
        return base
    return f"{base} {AI_DISCLAIMER}"


def post_auth_path(user: UserProfile) -> str:
    """First page after login based on legal + onboarding state."""
    if not policies_accepted(user):
        return "/legal/accept"
    if not user.onboarding_complete:
        return "/onboarding"
    return "/dashboard"