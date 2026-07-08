"""Format trust/vetting data for dashboard cards."""
from urllib.parse import urlparse

from app.services.ranking_service import DEFAULT_WEIGHTS, compute_fit_score
from app.services.vetting_service import compute_trust_summary


def _normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    raw = url.strip().rstrip("/")
    if not raw:
        return None
    if raw.startswith("http://"):
        raw = "https://" + raw[7:]
    elif not raw.startswith("https://"):
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/") or ""
    return f"{host}{path}".lower()


def _profile_source_url(profile) -> str | None:
    extracted = profile.extracted_data or {}
    url = extracted.get("profile_url")
    if url:
        return url
    username = (profile.username or "").strip()
    platform = (profile.platform or "").lower()
    if username and platform == "facebook":
        return f"https://facebook.com/{username}"
    return None


def _dedupe_profile_links(profile, enrichments: list) -> tuple[str | None, list]:
    """Hide source link when the same URL already appears in enrichment chips."""
    source_url = _profile_source_url(profile)
    normalized_source = _normalize_url(source_url)

    seen: set[str] = set()
    deduped: list = []
    for enrichment in enrichments:
        normalized = _normalize_url(getattr(enrichment, "url", None))
        if normalized:
            if normalized in seen:
                continue
            seen.add(normalized)
        deduped.append(enrichment)

    show_source = source_url
    if normalized_source and normalized_source in seen:
        show_source = None
    return show_source, deduped


def _first_not_none(*values):
    """Coalesce on None only — a legitimate score of 0 must survive."""
    for value in values:
        if value is not None:
            return value
    return None


def _normalized_weights_pct(weights: dict | None) -> dict:
    merged = {**DEFAULT_WEIGHTS, **(weights or {})}
    total = sum(
        merged.get(k, 0) for k in ("compatibility", "attractiveness", "red_flags")
    ) or 1.0
    return {
        k: round(100 * merged.get(k, 0) / total)
        for k in ("compatibility", "attractiveness", "red_flags")
    }


def _analysis_history(ranking) -> list[dict]:
    """Score snapshots + current state as display rows, newest first.

    Each row carries the match score at that time and its delta vs the prior
    analysis — the receipts for "why did her score change?".
    """
    history = list(getattr(ranking, "score_history", None) or [])
    if not history:
        return []
    entries = history + [
        {
            "at": None,
            "trigger": "Current",
            "overall": getattr(ranking, "overall_score", None),
        }
    ]
    rows: list[dict] = []
    prev: float | None = None
    for entry in entries:
        overall = entry.get("overall")
        delta = None
        if prev is not None and overall is not None:
            delta = round(overall - prev, 1)
        rows.append(
            {
                "at": (entry.get("at") or "")[:10],
                "trigger": entry.get("trigger") or "Analysis",
                "overall": overall,
                "delta": delta,
            }
        )
        if overall is not None:
            prev = overall
    rows.reverse()
    return rows


def _rank_note(ranking) -> str | None:
    """One honest sentence whenever list position differs from the match score."""
    feedback = getattr(ranking, "feedback", None)
    if feedback == "superlike":
        return "Pinned to top — your pick"
    if feedback == "like":
        return "Boosted — you liked this profile"
    if feedback == "dislike":
        return "Lowered — you passed"
    perc = getattr(ranking, "percolation_priority", None)
    overall = getattr(ranking, "overall_score", None) or 0
    if perc is not None and perc - overall >= 3:
        return "Boosted by X verification"
    if perc is not None and overall - perc >= 3:
        return "Lowered by X verification"
    return None


def trust_card_context(profile, ranking, preference=None) -> dict:
    trust = profile.trust_analysis or {}
    vetting = trust.get("vetting") or {}
    x_proof = _first_not_none(
        getattr(ranking, "x_social_proof_score", None),
        getattr(profile, "x_social_proof_score", None),
    )
    x_verification = getattr(profile, "x_verification", None) or {}
    trust_inputs = {
        "authenticity_score": _first_not_none(
            ranking.authenticity_score, profile.authenticity_score
        ),
        "naturalness_score": _first_not_none(
            ranking.naturalness_score, profile.naturalness_score
        ),
        "catfish_risk_score": _first_not_none(
            ranking.catfish_risk_score, profile.catfish_risk_score
        ),
        "bot_risk_score": _first_not_none(
            ranking.bot_risk_score, profile.bot_risk_score
        ),
        "x_social_proof_score": x_proof,
        "consistency_score": trust.get("consistency_score"),
        "risk_factors": trust.get("risk_factors", []),
        "social_mismatch": trust.get("social_mismatch", False),
        "photo_analyses": trust.get("photo_analyses"),
        "dimension_status": trust.get("dimension_status"),
        "catfish_analysis": trust.get("catfish_analysis"),
        "info_notes": trust.get("info_notes"),
    }
    # Always recompute: stored summaries predate X verification, confidence
    # tiers, and renormalized weights. The computation is cheap and pure.
    summary = compute_trust_summary(trust_inputs, vetting)

    loc = vetting.get("location") or {}
    web = vetting.get("web") or {}
    enrichments = list(profile.social_enrichments or [])
    web_socials = web.get("social_links") or []
    if not enrichments and web_socials:
        class _WebEnrichment:
            def __init__(self, link: dict):
                self.platform = link.get("platform", "web")
                self.url = link.get("url")
                self.summary = link.get("username") or "Web match"

        enrichments = [_WebEnrichment(link) for link in web_socials if link.get("url")]

    source_url, deduped_enrichments = _dedupe_profile_links(profile, enrichments)

    weights = getattr(preference, "weights", None)
    fit = compute_fit_score(
        {
            "compatibility_score": getattr(ranking, "compatibility_score", None),
            "attractiveness_score": getattr(ranking, "attractiveness_score", None),
            "red_flag_score": getattr(ranking, "red_flag_score", None),
        },
        weights,
    )

    return {
        "overall_trust": summary["overall_trust_score"],
        "catfish_flag": summary["catfish_flag"],
        "catfish_label": summary["catfish_flag_label"],
        "catfish_risk": summary["catfish_risk_score"],
        "confidence": summary.get("confidence"),
        "info_notes": summary.get("info_notes", []),
        "fit": fit,
        "trust_penalty": max(
            0.0, round(fit - (getattr(ranking, "overall_score", None) or 0), 1)
        ),
        "weights_pct": _normalized_weights_pct(weights),
        "rank_note": _rank_note(ranking),
        "history": _analysis_history(ranking),
        "auth": _first_not_none(ranking.authenticity_score, profile.authenticity_score),
        "natural": _first_not_none(ranking.naturalness_score, profile.naturalness_score),
        "bot": _first_not_none(ranking.bot_risk_score, profile.bot_risk_score),
        "x_proof": x_proof,
        "x_verification": x_verification or None,
        "x_verdict": x_verification.get("verdict"),
        "x_handle": x_verification.get("handle")
        or (
            profile.username
            if (profile.platform or "").lower() == "x"
            else (profile.extracted_data or {}).get("x_handle")
        ),
        "location_note": (
            loc.get("notes", [None])[0] if loc.get("notes") else None
        ),
        "location_ok": loc.get("consistent"),
        "web_url": web.get("search_url"),
        "web_status": web.get("status"),
        "risk_factors": summary.get("risk_factors", [])[:4],
        "source_url": source_url,
        "enrichments": deduped_enrichments,
        "enrichment_status": profile.enrichment_status,
    }