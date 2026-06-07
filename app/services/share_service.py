"""Build shareable analysis summaries with referral attribution."""
import base64
import hashlib
import hmac
import json
import logging
import time

from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models.profile import Profile, Ranking
from app.services import referral_service
from app.utils.social_meta import pick_share_hook, share_og_description
from app.utils.trust_display import trust_card_context

logger = logging.getLogger(__name__)
settings = get_settings()

SHARE_TTL_SECONDS = 30 * 86400


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64_decode(raw: str) -> bytes:
    pad = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + pad)


def create_share_token(account_id: int, ranking_id: int) -> str:
    payload = {
        "a": account_id,
        "r": ranking_id,
        "exp": int(time.time()) + SHARE_TTL_SECONDS,
    }
    body = _b64_encode(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(
        settings.secret_key.encode(), body.encode(), hashlib.sha256
    ).hexdigest()[:20]
    return f"{body}.{sig}"


def verify_share_token(token: str) -> tuple[int, int] | None:
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expected = hmac.new(
        settings.secret_key.encode(), body.encode(), hashlib.sha256
    ).hexdigest()[:20]
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_b64_decode(body))
        if payload.get("exp", 0) < time.time():
            return None
        return int(payload["a"]), int(payload["r"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def build_share_url(token: str) -> str:
    base = settings.app_url.rstrip("/")
    return f"{base}/share/{token}"


def _display_name(profile: Profile) -> str:
    return profile.name or profile.username or f"Profile #{profile.id}"


def format_share_text(
    profile: Profile,
    ranking: Ranking,
    trust: dict,
    *,
    share_url: str,
    referral_url: str,
    hook: str | None = None,
) -> str:
    lead = hook or pick_share_hook(ranking.id)
    lines = [
        f"{lead} — AI trust vetting on a dating profile",
        "",
        f"Trust {trust['overall_trust']:.0f}/100 · Match {ranking.overall_score:.0f}/100",
    ]
    if trust.get("catfish_risk") is not None:
        lines.append(f"Catfish risk {trust['catfish_risk']:.0f}%")

    lines.extend(
        [
            "",
            f"See the breakdown: {share_url}",
            "",
            f"Try MatchForge (bonus tokens): {referral_url}",
        ]
    )
    return "\n".join(lines)


def build_share_payload(db: Session, account_id: int, ranking_id: int) -> dict:
    ranking = (
        db.query(Ranking)
        .join(Profile, Ranking.profile_id == Profile.id)
        .options(joinedload(Ranking.profile).joinedload(Profile.social_enrichments))
        .filter(
            Ranking.id == ranking_id,
            Profile.account_id == account_id,
        )
        .first()
    )
    if not ranking:
        return {}

    profile = ranking.profile
    trust = trust_card_context(profile, ranking)
    referral = referral_service.get_referral_stats(db, account_id)
    referral_url = referral.get("referral_url") or referral_service.build_referral_url(
        referral.get("referral_code", "")
    )

    token = create_share_token(account_id, ranking_id)
    share_url = build_share_url(token)
    hook = pick_share_hook(ranking_id)
    text = format_share_text(
        profile,
        ranking,
        trust,
        share_url=share_url,
        referral_url=referral_url,
        hook=hook,
    )
    og_description = share_og_description(trust["overall_trust"], ranking.overall_score)

    return {
        "ranking_id": ranking_id,
        "profile_id": profile.id,
        "share_token": token,
        "share_url": share_url,
        "referral_url": referral_url,
        "text": text,
        "title": hook,
        "hook": hook,
        "og_description": og_description,
    }


def load_public_share(db: Session, token: str) -> dict | None:
    parsed = verify_share_token(token)
    if not parsed:
        return None
    account_id, ranking_id = parsed

    ranking = (
        db.query(Ranking)
        .join(Profile, Ranking.profile_id == Profile.id)
        .options(joinedload(Ranking.profile).joinedload(Profile.social_enrichments))
        .filter(
            Ranking.id == ranking_id,
            Profile.account_id == account_id,
        )
        .first()
    )
    if not ranking:
        return None

    profile = ranking.profile
    trust = trust_card_context(profile, ranking)
    referral = referral_service.get_referral_stats(db, account_id)

    hook = pick_share_hook(ranking_id)
    share_url = build_share_url(token)

    return {
        "profile": profile,
        "ranking": ranking,
        "trust": trust,
        "referral_url": referral.get("referral_url"),
        "referral_code": referral.get("referral_code"),
        "display_name": _display_name(profile),
        "share_hook": hook,
        "share_url": share_url,
        "og_title": hook,
        "og_description": share_og_description(
            trust["overall_trust"], ranking.overall_score
        ),
        "og_url": share_url,
        "twitter_title": hook,
        "twitter_description": share_og_description(
            trust["overall_trust"], ranking.overall_score
        ),
    }