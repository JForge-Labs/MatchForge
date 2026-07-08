"""Profile vetting: trust summary, location checks, and public web signals."""
import logging
import re
from urllib.parse import quote_plus

import httpx

from app.core.config import get_settings
from app.services.social_enrich_service import PLATFORM_URL_PATTERNS

logger = logging.getLogger(__name__)

LOCATION_RE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?),?\s*([A-Z]{2})\b"
)
CITY_RE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"
)


def _normalize_location(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower())


def _extract_locations_from_text(text: str | None) -> set[str]:
    if not text:
        return set()
    found: set[str] = set()
    for match in LOCATION_RE.findall(text):
        city, state = match
        found.add(_normalize_location(f"{city} {state}"))
        found.add(_normalize_location(city))
    for word in ("lives in", "from", "based in", "located in"):
        if word in text.lower():
            idx = text.lower().find(word)
            snippet = text[idx : idx + 60]
            for city in CITY_RE.findall(snippet):
                if len(city) > 2 and city.lower() not in ("the", "and", "for"):
                    found.add(_normalize_location(city))
    return found


def check_location_consistency(
    *,
    claimed_location: str | None,
    bio: str | None,
    extracted_data: dict | None,
) -> dict:
    """Compare claimed location against bio and extracted screenshot fields."""
    claimed = _normalize_location(claimed_location)
    bio_locs = _extract_locations_from_text(bio)
    extra_locs: set[str] = set()
    if extracted_data:
        for key in ("location", "bio", "prompts"):
            val = extracted_data.get(key)
            if isinstance(val, str):
                extra_locs |= _extract_locations_from_text(val)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        extra_locs |= _extract_locations_from_text(item)

    all_mentions = bio_locs | extra_locs
    if claimed:
        all_mentions.discard(claimed)

    consistent = True
    notes: list[str] = []
    if not claimed:
        notes.append("No location on profile")
        consistent = None  # unknown
    elif all_mentions:
        overlap = any(
            claimed in loc or loc in claimed for loc in all_mentions if loc
        )
        if not overlap:
            consistent = False
            notes.append(
                f"Bio mentions different area(s): {', '.join(sorted(all_mentions)[:3])}"
            )
        else:
            notes.append("Location consistent with bio")
    else:
        notes.append("No conflicting location signals in bio")

    return {
        "claimed_location": claimed_location,
        "bio_locations": sorted(all_mentions),
        "consistent": consistent,
        "notes": notes,
    }


def _extract_social_links(*texts: str) -> list[dict]:
    """Pull platform profile URLs from search result text."""
    links: list[dict] = []
    seen: set[str] = set()
    for raw in texts:
        if not raw:
            continue
        for platform, pattern in PLATFORM_URL_PATTERNS.items():
            for match in pattern.finditer(raw):
                username = match.group(1)
                if username.lower() in ("pages", "groups", "profile.php"):
                    continue
                url = match.group(0)
                if not url.startswith("http"):
                    url = f"https://{url.lstrip('/')}"
                key = f"{platform}:{username.lower()}"
                if key in seen:
                    continue
                seen.add(key)
                links.append(
                    {"platform": platform, "username": username, "url": url}
                )
    return links[:8]


async def _brave_web_search(query: str) -> dict | None:
    """General name/location search via Brave Web Search API."""
    if not get_settings().brave_api_key:
        return None
    findings: dict = {
        "status": "empty",
        "query": query,
        "search_url": f"https://search.brave.com/search?q={quote_plus(query)}",
        "snippets": [],
        "social_links": [],
        "provider": "brave",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": 12},
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": get_settings().brave_api_key,
                },
            )
            resp.raise_for_status()
            payload = resp.json()

        texts: list[str] = []
        for result in (payload.get("web") or {}).get("results") or []:
            title = result.get("title") or ""
            description = result.get("description") or ""
            url = result.get("url") or ""
            snippet = " ".join(p for p in (title, description) if p).strip()
            if snippet:
                findings["snippets"].append(snippet[:300])
            texts.extend([title, description, url])

        findings["social_links"] = _extract_social_links(*texts)
        findings["status"] = (
            "ok"
            if findings["snippets"] or findings["social_links"]
            else "empty"
        )
        return findings
    except Exception as exc:
        logger.warning("Brave web vetting search failed: %s", exc)
        return None


async def _duckduckgo_web_search(query: str) -> dict:
    """Fallback public web search when Brave is unavailable."""
    search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    snippets: list[str] = []
    link_texts: list[str] = []
    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "MatchForge-Vetting/1.0"},
        ) as client:
            resp = await client.get(search_url)
            resp.raise_for_status()
            html = resp.text
            for block in re.findall(
                r'class="result__snippet"[^>]*>([^<]+)<', html
            )[:5]:
                snippets.append(block.strip()[:300])
            link_texts = re.findall(
                r'class="result__a"[^>]*href="([^"]+)"', html
            )[:10]
        status = "ok" if snippets or link_texts else "empty"
    except Exception as exc:
        logger.warning("Web vetting search failed: %s", exc)
        status = "error"
        snippets = [str(exc)]

    return {
        "status": status,
        "query": query,
        "search_url": search_url,
        "snippets": snippets,
        "social_links": _extract_social_links(*snippets, *link_texts),
        "provider": "duckduckgo",
    }


async def web_footprint_search(
    name: str | None,
    location: str | None,
    *,
    username: str | None = None,
    platform: str | None = None,
) -> dict:
    """Public web search for vetting — Brave API preferred, DuckDuckGo fallback."""
    parts = [p for p in (name, location) if p]
    if username and username not in parts:
        parts.insert(0, username)
    if not parts:
        return {"status": "skipped", "snippets": [], "search_url": None, "social_links": []}

    query = " ".join(parts)
    brave = await _brave_web_search(query)
    result = brave if brave else await _duckduckgo_web_search(query)
    result.setdefault("social_links", [])

    location_hits: list[str] = []
    if location:
        loc_norm = _normalize_location(location)
        for snip in result.get("snippets") or []:
            if loc_norm and loc_norm.split()[0] in snip.lower():
                location_hits.append(snip[:120])
    result["location_mentions"] = location_hits
    result["query"] = query
    return result


# Published trust-dimension weights — /how-scoring-works must stay in sync.
TRUST_WEIGHTS = {
    "authenticity": 0.35,
    "naturalness": 0.15,
    "catfish": 0.30,
    "bot": 0.10,
    "consistency": 0.10,
}
X_PROOF_WEIGHT = 0.15


def _score_of(trust: dict, key: str) -> float | None:
    value = trust.get(key)
    return float(value) if value is not None else None


def _confidence(trust: dict, vetting: dict | None) -> dict:
    """Deterministic confidence tier from evidence volume, not vibes."""
    statuses = trust.get("dimension_status") or {}
    degraded = any(s == "unavailable" for s in statuses.values())

    photos = trust.get("photo_analyses") or []
    analyzed_photos = [
        p for p in photos if p.get("analysis_status", "analyzed") != "unavailable"
    ]
    core_present = sum(
        1
        for key in (
            "authenticity_score",
            "naturalness_score",
            "catfish_risk_score",
            "bot_risk_score",
        )
        if trust.get(key) is not None
    )
    has_x = trust.get("x_social_proof_score") is not None
    web = (vetting or {}).get("web") or {}
    has_web = web.get("status") == "ok"

    basis: list[str] = []
    if photos:
        n = len(analyzed_photos)
        basis.append(f"{n} photo{'s' if n != 1 else ''} analyzed")
    if trust.get("bot_risk_score") is not None:
        basis.append("bio/text signals")
    if has_x:
        basis.append("X verification")
    if has_web:
        basis.append("public web footprint")

    if degraded or core_present <= 2:
        tier = "low"
    elif core_present >= 4 and (has_x or len(analyzed_photos) >= 3):
        tier = "high"
    else:
        tier = "medium"
    if degraded:
        basis.append("some checks unavailable")

    return {"tier": tier, "basis": "Based on " + (", ".join(basis) or "limited data")}


def compute_trust_summary(trust: dict, vetting: dict | None = None) -> dict:
    """Overall trust score from whichever dimensions were actually analyzed.

    Each present dimension contributes its published weight, renormalized over
    the dimensions available — a missing analysis lowers confidence, never the
    score. Returns overall_trust_score=None when nothing was analyzed.
    """
    auth = _score_of(trust, "authenticity_score")
    natural = _score_of(trust, "naturalness_score")
    catfish = _score_of(trust, "catfish_risk_score")
    bot = _score_of(trust, "bot_risk_score")
    consistency = _score_of(trust, "consistency_score")
    x_proof = _score_of(trust, "x_social_proof_score")

    location_penalty = 0.0
    loc = (vetting or {}).get("location") or {}
    if loc.get("consistent") is False:
        location_penalty = 10.0

    components = [
        (auth, TRUST_WEIGHTS["authenticity"]),
        (natural, TRUST_WEIGHTS["naturalness"]),
        (100 - catfish if catfish is not None else None, TRUST_WEIGHTS["catfish"]),
        (100 - bot if bot is not None else None, TRUST_WEIGHTS["bot"]),
        (consistency, TRUST_WEIGHTS["consistency"]),
        (x_proof, X_PROOF_WEIGHT),
    ]
    present = [(v, w) for v, w in components if v is not None]
    if present:
        total_weight = sum(w for _, w in present)
        overall = (
            sum(v * w for v, w in present) / total_weight - location_penalty
        )
        overall = max(0.0, min(100.0, round(overall, 1)))
    else:
        overall = None

    if overall is None:
        flag, label = "unknown", "Not analyzed"
    elif (catfish is not None and catfish >= 60) or overall < 40:
        flag, label = "flag", "Catfish risk"
    elif x_proof is not None and x_proof < 30:
        flag, label = "caution", "Weak X social proof"
    elif (
        (catfish is not None and catfish >= 35)
        or overall < 60
        or location_penalty >= 10
    ):
        flag, label = "caution", "Verify further"
    elif x_proof is not None and x_proof >= 70:
        flag, label = "clear", "X-verified"
    else:
        flag, label = "clear", "Looks legit"

    risk_factors = list(trust.get("risk_factors") or [])
    if loc.get("consistent") is False:
        # A regex heuristic must never accuse anyone outright — hedge it.
        risk_factors.append(
            "Bio and profile mention different places — worth asking about"
        )
    if x_proof is not None and x_proof < 30:
        risk_factors.append("Weak social proof on X")

    info_notes = list(trust.get("info_notes") or [])
    catfish_info = (trust.get("catfish_analysis") or {}).get("info_notes") or []
    for note in catfish_info:
        if note not in info_notes:
            info_notes.append(note)

    return {
        "overall_trust_score": overall,
        "catfish_flag": flag,
        "catfish_flag_label": label,
        "catfish_risk_score": catfish,
        "x_social_proof_score": x_proof,
        "location_penalty": location_penalty,
        "risk_factors": risk_factors,
        "info_notes": info_notes,
        "confidence": _confidence(trust, vetting),
    }


async def vet_profile(
    *,
    name: str | None,
    bio: str | None,
    location: str | None,
    extracted_data: dict | None,
    trust_analysis: dict | None,
    social_enrichments: list | None = None,
    run_web_search: bool = True,
) -> dict:
    """Run local + web vetting checks; returns dict stored under trust_analysis.vetting."""
    location_check = check_location_consistency(
        claimed_location=location,
        bio=bio,
        extracted_data=extracted_data,
    )
    extracted = extracted_data or {}
    web = (
        await web_footprint_search(
            name,
            location,
            username=extracted.get("username"),
            platform=extracted.get("platform"),
        )
        if run_web_search
        else {"status": "skipped"}
    )

    social_signals: list[dict] = []
    for e in social_enrichments or []:
        findings = e.findings if hasattr(e, "findings") else e.get("findings", {})
        social_signals.append(
            {
                "platform": e.platform if hasattr(e, "platform") else e.get("platform"),
                "status": findings.get("status"),
                "usernames": findings.get("usernames", [])[:3],
                "summary": e.summary if hasattr(e, "summary") else e.get("summary"),
            }
        )

    vetting = {
        "location": location_check,
        "web": web,
        "social_signals": social_signals,
    }
    summary = compute_trust_summary(trust_analysis or {}, vetting)
    vetting["summary"] = summary
    return vetting


def merge_vetting_into_trust(trust: dict, vetting: dict) -> dict:
    """Attach vetting and recompute display fields on trust_analysis."""
    merged = {**trust, "vetting": vetting}
    summary = vetting.get("summary") or compute_trust_summary(merged, vetting)
    merged["overall_trust_score"] = summary["overall_trust_score"]
    merged["catfish_flag"] = summary["catfish_flag"]
    merged["catfish_flag_label"] = summary["catfish_flag_label"]
    merged["risk_factors"] = summary.get("risk_factors", merged.get("risk_factors", []))
    if summary["catfish_flag"] == "flag" and not merged.get("trust_explanation"):
        merged["trust_explanation"] = "High catfish risk — review vetting details"
    return merged