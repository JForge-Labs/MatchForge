"""Format trust/vetting data for dashboard cards."""
from app.services.vetting_service import compute_trust_summary


def trust_card_context(profile, ranking) -> dict:
    trust = profile.trust_analysis or {}
    vetting = trust.get("vetting") or {}
    summary = vetting.get("summary") or compute_trust_summary(
        {
            "authenticity_score": ranking.authenticity_score
            or profile.authenticity_score,
            "naturalness_score": ranking.naturalness_score
            or profile.naturalness_score,
            "catfish_risk_score": ranking.catfish_risk_score
            or profile.catfish_risk_score,
            "bot_risk_score": ranking.bot_risk_score or profile.bot_risk_score,
            "consistency_score": trust.get("consistency_score", 70),
            "risk_factors": trust.get("risk_factors", []),
            "social_mismatch": trust.get("social_mismatch", False),
        },
        vetting,
    )

    loc = vetting.get("location") or {}
    web = vetting.get("web") or {}
    enrichments = profile.social_enrichments or []

    return {
        "overall_trust": summary["overall_trust_score"],
        "catfish_flag": summary["catfish_flag"],
        "catfish_label": summary["catfish_flag_label"],
        "catfish_risk": summary["catfish_risk_score"],
        "auth": ranking.authenticity_score or profile.authenticity_score,
        "natural": ranking.naturalness_score or profile.naturalness_score,
        "bot": ranking.bot_risk_score or profile.bot_risk_score,
        "location_note": (
            loc.get("notes", [None])[0] if loc.get("notes") else None
        ),
        "location_ok": loc.get("consistent"),
        "web_url": web.get("search_url"),
        "web_status": web.get("status"),
        "risk_factors": summary.get("risk_factors", [])[:4],
        "enrichments": enrichments,
        "enrichment_status": profile.enrichment_status,
    }