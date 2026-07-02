"""Official X API v2 client — deterministic ground truth for X verification.

Two complementary X data paths power MatchForge's verification:
  1. This module — the official X API (user lookup, timelines, recent search)
     for hard facts: account age, follower ratios, posting cadence, verified
     status, profile image.
  2. Grok's server-side ``x_search`` tool (see ``llm_service.generate_agentic``)
     for the qualitative agentic sweep.

Results are cached in the ``x_profiles`` table (TTL) so repeat verifications
don't re-bill pay-per-use post reads. Everything here reads PUBLIC data only.
"""
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.x_profile import XProfileCache

logger = logging.getLogger(__name__)

X_API_BASE = "https://api.x.com/2"

USER_FIELDS = (
    "created_at,description,location,name,profile_image_url,protected,"
    "public_metrics,url,verified,verified_type,entities"
)
TWEET_FIELDS = "created_at,public_metrics,referenced_tweets,entities,lang"

HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.x_api_enabled and settings.x_bearer_token)


def normalize_handle(raw: str | None) -> str | None:
    """Accept '@handle', bare handle, or an x.com/twitter.com URL."""
    if not raw:
        return None
    value = raw.strip()
    url_match = re.search(
        r"(?:twitter\.com|x\.com)/@?([A-Za-z0-9_]{1,15})", value, re.I
    )
    if url_match:
        value = url_match.group(1)
    value = value.lstrip("@").strip().strip("/")
    if not HANDLE_RE.match(value):
        return None
    reserved = {"home", "search", "explore", "i", "intent", "share", "hashtag"}
    if value.lower() in reserved:
        return None
    return value


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().x_bearer_token}"}


async def lookup_user(username: str) -> dict | None:
    """GET /2/users/by/username/:username — public account facts."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{X_API_BASE}/users/by/username/{username}",
            params={"user.fields": USER_FIELDS},
            headers=_headers(),
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        body = resp.json()
    if body.get("errors") and not body.get("data"):
        return None
    return body.get("data")


async def fetch_timeline(x_user_id: str, *, max_results: int | None = None) -> list[dict]:
    """GET /2/users/:id/tweets — recent public posts (billed per post read)."""
    settings = get_settings()
    limit = min(max(5, max_results or settings.x_timeline_max_posts), 100)
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{X_API_BASE}/users/{x_user_id}/tweets",
            params={"max_results": limit, "tweet.fields": TWEET_FIELDS},
            headers=_headers(),
        )
        resp.raise_for_status()
        body = resp.json()
    return body.get("data") or []


async def search_mentions(username: str, *, max_results: int = 10) -> list[dict]:
    """GET /2/tweets/search/recent — what others say about this handle (7 days)."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{X_API_BASE}/tweets/search/recent",
            params={
                "query": f"@{username} -from:{username}",
                "max_results": max(10, min(max_results, 100)),
                "tweet.fields": TWEET_FIELDS,
            },
            headers=_headers(),
        )
        resp.raise_for_status()
        body = resp.json()
    return body.get("data") or []


def _parse_x_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def compute_x_signals(user_data: dict, timeline: list[dict]) -> dict:
    """Deterministic social-proof signals from official X API data (no LLM).

    Returns a signal breakdown plus ``deterministic_score`` (0-100, higher =
    stronger social proof). Mirrors the blended-scoring pattern in
    ``trust_service.compute_trust_adjusted_scores``.
    """
    now = datetime.now(timezone.utc)
    metrics = user_data.get("public_metrics") or {}
    followers = int(metrics.get("followers_count") or 0)
    following = int(metrics.get("following_count") or 0)
    tweet_count = int(metrics.get("tweet_count") or 0)
    listed = int(metrics.get("listed_count") or 0)

    signals: list[str] = []
    score = 50.0

    created = _parse_x_time(user_data.get("created_at"))
    account_age_days = (now - created).days if created else None
    if account_age_days is not None:
        if account_age_days >= 5 * 365:
            score += 20
            signals.append(f"Account is {account_age_days // 365} years old")
        elif account_age_days >= 365:
            score += 10
            signals.append(f"Account is {account_age_days // 365}+ year(s) old")
        elif account_age_days < 90:
            score -= 25
            signals.append(f"Account only {account_age_days} days old — new-account risk")
        elif account_age_days < 365:
            score -= 8
            signals.append("Account under a year old")

    ratio = followers / following if following else float(followers or 0)
    if followers >= 100 and ratio >= 0.5:
        score += 8
        signals.append("Healthy follower/following ratio")
    elif following > 1000 and ratio < 0.05:
        score -= 12
        signals.append("Follows many, followed by few — follow-farm pattern")

    if listed >= 5:
        score += 4
        signals.append("Listed by other users")

    if user_data.get("verified"):
        score += 8
        signals.append(f"Verified ({user_data.get('verified_type') or 'legacy'})")

    if user_data.get("protected"):
        signals.append("Account is protected — limited public visibility")

    default_image = "default_profile" in (user_data.get("profile_image_url") or "")
    if default_image:
        score -= 10
        signals.append("Default profile image")

    if not (user_data.get("description") or "").strip():
        score -= 5
        signals.append("Empty bio")

    # Posting cadence from the recent timeline
    post_times = sorted(
        t for t in (_parse_x_time(p.get("created_at")) for p in timeline) if t
    )
    posts_seen = len(post_times)
    if posts_seen >= 2:
        span_days = max((post_times[-1] - post_times[0]).days, 1)
        per_day = posts_seen / span_days
        if per_day > 40:
            score -= 15
            signals.append(f"Burst posting (~{per_day:.0f}/day) — automation pattern")
        elif 0.05 <= per_day <= 20:
            score += 8
            signals.append("Natural posting cadence")
        days_since_last = (now - post_times[-1]).days
        if days_since_last > 180:
            score -= 6
            signals.append(f"Dormant — last post {days_since_last} days ago")
    elif tweet_count == 0:
        score -= 10
        signals.append("Never posted")
    elif posts_seen == 0:
        signals.append("No recent public posts")

    if tweet_count > 0 and account_age_days:
        lifetime_per_day = tweet_count / max(account_age_days, 1)
        if lifetime_per_day > 60:
            score -= 10
            signals.append("Extreme lifetime posting volume")

    # Original content vs pure retweets in recent timeline
    if timeline:
        retweets = sum(
            1
            for p in timeline
            if any(
                r.get("type") == "retweeted"
                for r in (p.get("referenced_tweets") or [])
            )
        )
        if retweets == len(timeline) and len(timeline) >= 5:
            score -= 8
            signals.append("Recent activity is 100% retweets — no original voice")

    return {
        "deterministic_score": round(max(0.0, min(100.0, score)), 1),
        "signals": signals,
        "account_age_days": account_age_days,
        "followers": followers,
        "following": following,
        "tweet_count": tweet_count,
        "listed_count": listed,
        "verified": bool(user_data.get("verified")),
        "protected": bool(user_data.get("protected")),
        "default_profile_image": default_image,
        "recent_posts_sampled": posts_seen,
    }


def _cache_fresh(row: XProfileCache) -> bool:
    fetched = row.fetched_at
    if fetched is None:
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    ttl = timedelta(hours=get_settings().x_cache_ttl_hours)
    return datetime.now(timezone.utc) - fetched < ttl


async def fetch_x_profile(
    db: Session, username: str, *, force_refresh: bool = False
) -> dict:
    """Fetch (cached) public X profile facts + timeline + deterministic signals.

    Returns a dict with ``status`` one of:
      ok | not_found | unavailable (no key) | error
    """
    handle = normalize_handle(username)
    if not handle:
        return {"status": "error", "detail": "Invalid X handle"}
    if not is_configured():
        return {"status": "unavailable", "username": handle}

    row = (
        db.query(XProfileCache)
        .filter(XProfileCache.username == handle.lower())
        .first()
    )
    if row and not force_refresh and _cache_fresh(row):
        if not row.user_data:
            return {"status": "not_found", "username": handle, "cached": True}
        return {
            "status": "ok",
            "username": handle,
            "cached": True,
            "user": row.user_data,
            "timeline": row.timeline or [],
            "signals": row.signals or {},
        }

    try:
        user = await lookup_user(handle)
    except httpx.HTTPError as exc:
        logger.warning("X user lookup failed for @%s: %s", handle, exc)
        return {"status": "error", "username": handle, "detail": str(exc)}

    timeline: list[dict] = []
    signals: dict = {}
    if user:
        if not user.get("protected"):
            try:
                timeline = await fetch_timeline(user["id"])
            except httpx.HTTPError as exc:
                logger.warning("X timeline fetch failed for @%s: %s", handle, exc)
        signals = compute_x_signals(user, timeline)

    if row is None:
        row = XProfileCache(username=handle.lower())
        db.add(row)
    row.x_user_id = (user or {}).get("id")
    row.user_data = user or {}
    row.timeline = timeline
    row.signals = signals
    row.fetched_at = datetime.now(timezone.utc)
    db.flush()

    if not user:
        return {"status": "not_found", "username": handle}
    return {
        "status": "ok",
        "username": handle,
        "cached": False,
        "user": user,
        "timeline": timeline,
        "signals": signals,
    }


async def fetch_profile_image(user_data: dict) -> bytes | None:
    """Download the X profile image (public CDN) for photo cross-checking."""
    url = user_data.get("profile_image_url")
    if not url:
        return None
    # X serves a small "_normal" variant by default; request the full-size one.
    url = url.replace("_normal.", "_400x400.")
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content
    except httpx.HTTPError as exc:
        logger.warning("X profile image fetch failed: %s", exc)
        return None
