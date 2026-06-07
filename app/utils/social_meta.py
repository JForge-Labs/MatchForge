"""Open Graph / homescreen link preview helpers."""
from app.core.config import get_settings

SHARE_HOOKS = (
    "Check this one out",
    "Worth a look",
    "Someone sent you a vetting summary",
    "See what the AI flagged",
    "Run this through MatchForge?",
)

REFERRAL_OG_TITLE = "You're invited to MatchForge"
REFERRAL_OG_DESCRIPTION = (
    "Upload dating screenshots, get AI trust vetting and ranked shortlists. "
    "Sign up with this link for bonus tokens."
)

SITE_OG_TITLE = "MatchForge — AI dating intelligence"
SITE_OG_DESCRIPTION = (
    "Privacy-first match intelligence — upload profiles, vet trust signals, "
    "and rank by compatibility tailored to your goals."
)


def absolute_url(path: str) -> str:
    base = get_settings().app_url.rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def og_image_url() -> str:
    return absolute_url("/static/icons/og-card.png")


def icon_url(size: int = 512) -> str:
    return absolute_url(f"/static/icons/icon-{size}.png")


def pick_share_hook(ranking_id: int) -> str:
    return SHARE_HOOKS[ranking_id % len(SHARE_HOOKS)]


def share_og_description(trust_score: float, match_score: float) -> str:
    return (
        f"Trust {trust_score:.0f} · Match {match_score:.0f} — "
        "AI-vetted dating profile breakdown"
    )