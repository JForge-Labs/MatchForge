"""Match uploads to existing profile tiles and merge evidence organically."""
import logging
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.profile import Profile, Ranking
from app.services.profile_extract_service import _clean_username

logger = logging.getLogger(__name__)


def identity_key(
    platform: str | None,
    username: str | None,
    name: str | None,
    profile_url: str | None = None,
) -> str | None:
    """Stable key for deduping profiles within an account."""
    plat = (platform or "other").lower().strip()
    user = _clean_username(username)
    if user:
        return f"{plat}:{user.lower()}"
    url_user = _username_from_profile_url(profile_url, plat)
    if url_user:
        return f"{plat}:{url_user.lower()}"
    clean_name = _normalize_name(name)
    if clean_name and plat != "other":
        return f"{plat}:name:{clean_name}"
    if clean_name:
        return f"name:{clean_name}"
    return None


def _normalize_name(name: str | None) -> str | None:
    if not name:
        return None
    name = name.strip()
    if not name or name.lower() in ("unknown", "null", "none", "n/a"):
        return None
    return re.sub(r"\s+", " ", name).lower()


def _username_from_profile_url(url: str | None, platform: str) -> str | None:
    if not url:
        return None
    from app.services.profile_extract_service import USERNAME_URL_PATTERNS

    for pattern, plat in USERNAME_URL_PATTERNS:
        if plat != platform and platform != "other":
            continue
        match = re.search(pattern, url, re.I)
        if match:
            return _clean_username(match.group(1))
    return None


def find_existing_profile(
    db: Session, account_id: int, analysis: dict
) -> Profile | None:
    """Find an existing tile for the same person (platform + username/name)."""
    key = identity_key(
        analysis.get("platform"),
        analysis.get("username"),
        analysis.get("name"),
        analysis.get("profile_url"),
    )
    if not key:
        return None

    candidates = (
        db.query(Profile)
        .filter(Profile.account_id == account_id)
        .order_by(Profile.updated_at.desc())
        .all()
    )
    for profile in candidates:
        existing = identity_key(
            profile.platform,
            profile.username,
            profile.name,
            (profile.extracted_data or {}).get("profile_url"),
        )
        if existing and existing == key:
            return profile
    return None


def _pick_richer(current: str | None, new: str | None) -> str | None:
    if not new or not str(new).strip():
        return current
    if not current or not str(current).strip():
        return new
    return new if len(str(new)) > len(str(current)) else current


def _merge_list_fields(existing: list, new_items: list, limit: int = 20) -> list:
    seen: set[str] = set()
    merged: list = []
    for item in (existing or []) + (new_items or []):
        if item is None:
            continue
        key = str(item).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged[-limit:]


def merge_analysis_into_profile(
    profile: Profile,
    analysis: dict,
    *,
    photo_path: str | None = None,
    photo_index: int = 0,
) -> None:
    """Enrich an existing profile with new screenshot extraction (no duplicate tile)."""
    profile.name = _pick_richer(profile.name, analysis.get("name"))
    profile.username = _pick_richer(profile.username, analysis.get("username")) or profile.username
    profile.bio = _pick_richer(profile.bio, analysis.get("bio"))
    profile.age = analysis.get("age") or profile.age
    profile.location = _pick_richer(profile.location, analysis.get("location"))
    profile.platform = analysis.get("platform") or profile.platform

    extracted = dict(profile.extracted_data or {})
    for key, val in analysis.items():
        if val is None:
            continue
        if key in ("red_flags", "green_flags", "prompts", "interests"):
            extracted[key] = _merge_list_fields(extracted.get(key), val if isinstance(val, list) else [val])
        elif key not in extracted or not extracted.get(key):
            extracted[key] = val
    uploads = extracted.get("upload_history") or []
    uploads.append(
        {
            "photo_index": photo_index,
            "path": photo_path,
            "platform": analysis.get("platform"),
            "confidence": analysis.get("confidence"),
        }
    )
    extracted["upload_history"] = uploads[-15:]
    profile.extracted_data = extracted

    vision = dict(profile.vision_analysis or {})
    vision.update({k: v for k, v in analysis.items() if v is not None})
    profile.vision_analysis = vision

    photos = list(profile.photos or [])
    if photo_path and not any(p.get("path") == photo_path for p in photos):
        photos.append({"path": photo_path, "index": photo_index})
    profile.photos = photos


def merge_trust_into_profile(profile: Profile, trust: dict) -> None:
    """Blend new trust analysis into profile, keeping per-photo history."""
    prior = profile.trust_analysis or {}
    prior_photos = list(prior.get("photo_analyses") or [])
    new_photos = list(trust.get("photo_analyses") or [])
    merged_photos = prior_photos + new_photos

    # Forensics are cached per photo_path (newest wins) so re-analysis of a
    # merged profile never duplicates entries or re-runs vision on old photos.
    deduped: list[dict] = []
    seen_paths: set[str] = set()
    for photo in reversed(merged_photos):
        path = photo.get("photo_path") if isinstance(photo, dict) else None
        if path:
            if path in seen_paths:
                continue
            seen_paths.add(path)
        deduped.append(photo)
    deduped.reverse()

    profile.trust_analysis = {**prior, **trust, "photo_analyses": deduped[-10:]}
    profile.authenticity_score = trust.get("authenticity_score")
    profile.naturalness_score = trust.get("naturalness_score")
    profile.catfish_risk_score = trust.get("catfish_risk_score")
    profile.bot_risk_score = trust.get("bot_risk_score")


def load_profile_photo_bytes(profile: Profile) -> list[bytes]:
    """Load stored screenshots for re-trust analysis."""
    images: list[bytes] = []
    for photo in profile.photos or []:
        path = photo.get("path")
        if not path:
            continue
        p = Path(path)
        if p.is_file():
            images.append(p.read_bytes())
    return images


def dedupe_shortlist_rankings(rankings: list[Ranking]) -> list[Ranking]:
    """Keep highest-priority ranking per profile identity (dashboard hygiene)."""
    best: dict[str, Ranking] = {}
    order: list[str] = []
    for ranking in rankings:
        profile = ranking.profile
        key = identity_key(
            profile.platform,
            profile.username,
            profile.name,
            (profile.extracted_data or {}).get("profile_url"),
        ) or f"id:{profile.id}"
        if key not in best:
            order.append(key)
            best[key] = ranking
            continue
        if ranking.percolation_priority > best[key].percolation_priority:
            best[key] = ranking
    return [best[k] for k in order]


def merge_duplicate_profiles(db: Session, account_id: int | None = None) -> int:
    """Merge duplicate profile rows; keep richest record, re-point rankings."""
    q = db.query(Profile)
    if account_id is not None:
        q = q.filter(Profile.account_id == account_id)
    profiles = q.order_by(Profile.id).all()

    groups: dict[str, list[Profile]] = {}
    for profile in profiles:
        key = identity_key(
            profile.platform,
            profile.username,
            profile.name,
            (profile.extracted_data or {}).get("profile_url"),
        )
        if not key:
            continue
        groups.setdefault(key, []).append(profile)

    merged_count = 0
    for key, group in groups.items():
        if len(group) < 2:
            continue
        keeper = max(group, key=lambda p: (len(p.photos or []), p.updated_at or p.created_at))
        dupes = [p for p in group if p.id != keeper.id]
        for dupe in dupes:
            for photo in dupe.photos or []:
                if photo not in (keeper.photos or []):
                    keeper.photos = (keeper.photos or []) + [photo]
            merge_analysis_into_profile(keeper, dupe.extracted_data or {})
            merge_analysis_into_profile(keeper, dupe.vision_analysis or {})
            if dupe.trust_analysis:
                merge_trust_into_profile(keeper, dupe.trust_analysis)

            dupe_ranking = db.query(Ranking).filter(Ranking.profile_id == dupe.id).first()
            keeper_ranking = db.query(Ranking).filter(Ranking.profile_id == keeper.id).first()
            if dupe_ranking and keeper_ranking:
                if dupe_ranking.percolation_priority > keeper_ranking.percolation_priority:
                    keeper_ranking.percolation_priority = dupe_ranking.percolation_priority
                    keeper_ranking.overall_score = max(
                        keeper_ranking.overall_score, dupe_ranking.overall_score
                    )
                db.delete(dupe_ranking)
            elif dupe_ranking:
                dupe_ranking.profile_id = keeper.id

            db.delete(dupe)
            merged_count += 1
            logger.info("Merged duplicate profile %s into %s (%s)", dupe.id, keeper.id, key)

    if merged_count:
        db.commit()
    return merged_count