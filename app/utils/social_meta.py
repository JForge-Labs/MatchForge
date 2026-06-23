"""Open Graph / homescreen link preview helpers."""
from app.core.config import get_settings

SHARE_HOOKS = (
    "AI trust vetting on a dating profile",
    "MatchForge profile breakdown",
    "Private dating due diligence",
    "Compatibility and trust signals",
    "Vetting summary from MatchForge",
)

REFERRAL_OG_TITLE = "You're invited to MatchForge"
REFERRAL_OG_DESCRIPTION = (
    "Upload dating screenshots, get AI trust vetting and ranked shortlists. "
    "Sign up with this link for bonus tokens."
)

SITE_OG_TITLE = "MatchForge — AI dating intelligence"
SITE_OG_DESCRIPTION = (
    "Personal safety due diligence for dating — upload screenshots, vet trust signals, "
    "and get a private ranked shortlist tailored to your goals."
)

SHARE_EXPIRED_OG_TITLE = "This share has expired — MatchForge"
SHARE_EXPIRED_OG_DESCRIPTION = (
    "We value everyone's privacy. Shared profile breakdowns are time-limited. "
    "Join MatchForge to vet dating profiles with AI."
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