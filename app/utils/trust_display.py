"""Format trust/vetting data for dashboard cards."""
from urllib.parse import urlparse

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


def trust_card_context(profile, ranking) -> dict:
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
        "consistency_score": trust.get("consistency_score", 70),
        "risk_factors": trust.get("risk_factors", []),
        "social_mismatch": trust.get("social_mismatch", False),
    }
    # Stored vetting summaries predate X verification — recompute when present
    if x_proof is not None:
        summary = compute_trust_summary(trust_inputs, vetting)
    else:
        summary = vetting.get("summary") or compute_trust_summary(
            trust_inputs, vetting
        )

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

    return {
        "overall_trust": summary["overall_trust_score"],
        "catfish_flag": summary["catfish_flag"],
        "catfish_label": summary["catfish_flag_label"],
        "catfish_risk": summary["catfish_risk_score"],
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