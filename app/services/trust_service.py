"""Authenticity, catfish, filter, and bot-trust scoring orchestration."""
import json
import logging
import re

from app.core.config import get_settings
from app.services import llm_service, vetting_service, vision_service

logger = logging.getLogger(__name__)
settings = get_settings()

BOT_DETECTION_PROMPT = """Analyze this dating profile text for bot, fake, or spam signals.

PROFILE DATA:
{bio_and_metadata}

Return ONLY valid JSON:
{{
  "bot_risk_score": 0-100 (higher = more likely bot/fake/spam),
  "signals": ["specific bot/fake indicators found"],
  "bio_quality": "high|medium|low",
  "template_likelihood": 0-100,
  "explanation": "1-2 sentences on bot/fake assessment"
}}

Calibration — important:
- Default toward LOW scores (15-30) for profiles that look like normal humans with any personal detail.
- Only score 50+ when you see MULTIPLE strong bot/spam indicators together.
- Generic dating clichés alone (e.g. "love to laugh") are weak signals — max +10, not grounds for high risk.
- Short bios are common on real profiles — do not penalize heavily unless empty or link-only.
- Reserve 70+ for clear scam patterns, link funnels, crypto pitches, or obviously automated spam."""

CATFISH_SYNTHESIS_PROMPT = """Synthesize catfish/authenticity risk from photo analyses, bio, and social signals.

PHOTO TRUST ANALYSES:
{photo_analyses}

BIO: {bio}

SOCIAL ENRICHMENT:
{social_findings}

Return ONLY valid JSON:
{{
  "catfish_risk_score": 0-100 (higher = higher catfish/scam risk),
  "authenticity_score": 0-100 (higher = more confident they are who they claim),
  "consistency_score": 0-100 (photo-to-photo and photo-to-bio consistency),
  "social_mismatch": true/false,
  "risk_factors": ["list of specific concerns"],
  "trust_explanation": "Clear user-facing explanation e.g. 'High catfish risk — photos appear AI-generated'"
}}"""


def _parse_json_response(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        brace = re.search(r"\{[\s\S]*\}", text)
        if brace:
            return json.loads(brace.group())
        raise


def _trust_badge(score: float, invert: bool = False) -> str:
    """Return green/yellow/red for display."""
    effective = 100 - score if invert else score
    if effective >= 70:
        return "green"
    if effective >= 40:
        return "yellow"
    return "red"


def _fallback_photo_trust() -> dict:
    return {
        "authenticity_score": 50,
        "ai_generated_likelihood": 30,
        "filter_heaviness": 30,
        "naturalness_score": 60,
        "editing_tools_detected": [],
        "visual_red_flags": [],
        "explanation": "Trust analysis unavailable — neutral scores applied.",
    }


def _fallback_bot_risk(bio: str | None) -> dict:
    risk = 15
    signals = []
    if not bio or len(bio.strip()) < 8:
        risk += 12
        signals.append("Empty or very short bio")
    generic = ["love to laugh", "partner in crime", "ask me anything", "here for a good time"]
    if bio:
        lower = bio.lower()
        hits = [g for g in generic if g in lower]
        if hits:
            risk += 6 * min(len(hits), 2)
            signals.append(f"Common phrases: {', '.join(hits)}")
    risk = min(45, risk)
    return {
        "bot_risk_score": risk,
        "signals": signals,
        "bio_quality": "low" if risk > 40 else "medium",
        "template_likelihood": min(50, risk),
        "explanation": "Heuristic bot check — LLM unavailable.",
    }


def _calibrate_bot_risk(result: dict, bio: str | None) -> dict:
    """Dampen false positives on likely-real profiles."""
    score = float(result.get("bot_risk_score") or 20)
    signals = list(result.get("signals") or [])
    text = (bio or "").strip()

    if len(text) >= 40:
        score = min(score, max(20, score * 0.72))
    elif len(text) >= 20:
        score = min(score, max(18, score * 0.8))

    weak_only = signals and all(
        any(w in s.lower() for w in ("generic", "common", "short", "minimal", "clich"))
        for s in signals
    )
    if weak_only and score > 35:
        score = 35

    if score < 25 and signals:
        signals = signals[:1]

    result = dict(result)
    result["bot_risk_score"] = round(max(0, min(100, score)), 1)
    result["signals"] = signals
    if result["bot_risk_score"] < 40:
        result["explanation"] = (
            result.get("explanation") or "No strong bot indicators."
        ).replace("Bot risk:", "").strip() or "Looks like a normal profile."
    return result


async def analyze_profile_trust(
    image_bytes_list: list[bytes],
    bio: str | None = None,
    profile_metadata: dict | None = None,
    social_enrichments: list | None = None,
) -> dict:
    """Full trust pipeline: per-photo vision + bot text + catfish synthesis."""
    photo_analyses: list[dict] = []
    for img in image_bytes_list:
        auth = await vision_service.analyze_authenticity(img)
        filters = await vision_service.detect_filters_and_edits(img)
        merged = {**auth, **filters}
        photo_analyses.append(merged)

    bot = await detect_bot_signals(bio, profile_metadata or {})

    catfish = await assess_catfish_risk(
        photo_analyses, bio, social_enrichments or []
    )

    auth_scores = [p.get("authenticity_score", 50) for p in photo_analyses]
    nat_scores = [p.get("naturalness_score", 50) for p in photo_analyses]
    ai_scores = [p.get("ai_generated_likelihood", 30) for p in photo_analyses]
    filter_scores = [p.get("filter_heaviness", 30) for p in photo_analyses]

    authenticity = catfish.get("authenticity_score") or (
        round(sum(auth_scores) / len(auth_scores), 1) if auth_scores else 50
    )
    naturalness = round(sum(nat_scores) / len(nat_scores), 1) if nat_scores else 50
    catfish_risk = catfish.get("catfish_risk_score", 30)
    bot_risk = bot.get("bot_risk_score", 20)

    explanations = []
    if catfish.get("trust_explanation"):
        explanations.append(catfish["trust_explanation"])
    if bot.get("explanation") and bot_risk >= 55:
        explanations.append(f"Bot risk: {bot['explanation']}")
    for p in photo_analyses:
        if p.get("ai_generated_likelihood", 0) >= 60:
            explanations.append("Photos show signs of AI generation")
            break
        if p.get("filter_heaviness", 0) >= 60:
            explanations.append("Heavy beauty filters or editing detected")
            break

    trust_explanation = " ".join(explanations) or "No major trust concerns flagged."

    result = {
        "authenticity_score": authenticity,
        "naturalness_score": naturalness,
        "catfish_risk_score": catfish_risk,
        "bot_risk_score": bot_risk,
        "ai_generated_likelihood": max(ai_scores) if ai_scores else 0,
        "filter_heaviness": max(filter_scores) if filter_scores else 0,
        "consistency_score": catfish.get("consistency_score", 70),
        "social_mismatch": catfish.get("social_mismatch", False),
        "trust_explanation": trust_explanation,
        "trust_badge": _trust_badge(authenticity),
        "catfish_badge": _trust_badge(catfish_risk, invert=True),
        "bot_badge": _trust_badge(bot_risk, invert=True),
        "photo_analyses": photo_analyses,
        "bot_analysis": bot,
        "catfish_analysis": catfish,
        "risk_factors": catfish.get("risk_factors", [])
        + (bot.get("signals", []) if bot_risk >= 50 else []),
    }
    summary = vetting_service.compute_trust_summary(result)
    result["overall_trust_score"] = summary["overall_trust_score"]
    result["catfish_flag"] = summary["catfish_flag"]
    result["catfish_flag_label"] = summary["catfish_flag_label"]
    return result


async def detect_bot_signals(
    bio: str | None, profile_metadata: dict
) -> dict:
    """Detect bot/fake patterns in profile text via LLM."""
    payload_text = json.dumps(
        {"bio": bio, **profile_metadata}, indent=2
    )
    prompt = BOT_DETECTION_PROMPT.format(bio_and_metadata=payload_text)
    try:
        result, _usage = await llm_service.generate_json(
            prompt, model=settings.xai_text_fast, timeout=120.0
        )
        return _calibrate_bot_risk(result, bio)
    except Exception as exc:
        logger.warning("Bot detection failed: %s", exc)
        return _fallback_bot_risk(bio)


async def assess_catfish_risk(
    photo_analyses: list[dict],
    bio: str | None,
    social_enrichments: list,
) -> dict:
    """Synthesize catfish risk from photos, bio, and social enrichment."""
    social_summary = []
    social_mismatch = False
    for e in social_enrichments:
        findings = e.findings if hasattr(e, "findings") else e.get("findings", {})
        status = findings.get("status", "unknown")
        snippets = findings.get("snippets", [])
        usernames = findings.get("usernames", [])
        platform = e.platform if hasattr(e, "platform") else e.get("platform", "")
        social_summary.append({
            "platform": platform,
            "status": status,
            "usernames_found": usernames,
            "result_count": len(snippets),
        })
        if status == "ok" and not usernames and not snippets:
            social_mismatch = True

    if not photo_analyses:
        return {
            "catfish_risk_score": 40,
            "authenticity_score": 50,
            "consistency_score": 50,
            "social_mismatch": social_mismatch,
            "risk_factors": ["No photos to analyze"],
            "trust_explanation": "Insufficient photo data for authenticity check.",
        }

    prompt = CATFISH_SYNTHESIS_PROMPT.format(
        photo_analyses=json.dumps(photo_analyses, indent=2),
        bio=bio or "(no bio)",
        social_findings=json.dumps(social_summary, indent=2),
    )
    try:
        result, _usage = await llm_service.generate_json(
            prompt, model=settings.xai_text_reason, timeout=180.0
        )
    except Exception as exc:
        logger.warning("Catfish synthesis failed: %s", exc)
        ai_max = max(p.get("ai_generated_likelihood", 0) for p in photo_analyses)
        auth_avg = sum(p.get("authenticity_score", 50) for p in photo_analyses) / len(
            photo_analyses
        )
        risk = min(100, (100 - auth_avg) * 0.5 + ai_max * 0.4 + (20 if social_mismatch else 0))
        result = {
            "catfish_risk_score": round(risk, 1),
            "authenticity_score": round(auth_avg, 1),
            "consistency_score": 60,
            "social_mismatch": social_mismatch,
            "risk_factors": [],
            "trust_explanation": (
                "High catfish risk — profile photos show authenticity concerns"
                if risk >= 60
                else "Moderate authenticity — heuristic assessment"
            ),
        }

    if social_mismatch:
        result["social_mismatch"] = True
        factors = result.get("risk_factors", [])
        if "No public social footprint found" not in factors:
            factors.append("No public social footprint found")
        result["risk_factors"] = factors
        if result.get("catfish_risk_score", 0) < 50:
            result["catfish_risk_score"] = min(100, result.get("catfish_risk_score", 0) + 15)

    return result


def apply_social_trust_adjustment(
    trust_analysis: dict, social_enrichments: list, vetting: dict | None = None
) -> dict:
    """Re-score trust after social enrichment and vetting complete."""
    return vetting_service.merge_vetting_into_trust(
        trust_analysis, vetting or trust_analysis.get("vetting", {})
    )


def compute_trust_adjusted_scores(
    base_scores: dict, trust: dict
) -> dict:
    """Blend trust signals into overall score and percolation priority."""
    base_overall = base_scores.get("overall_score", 50)
    auth = trust.get("authenticity_score", 50)
    natural = trust.get("naturalness_score", 50)
    catfish = trust.get("catfish_risk_score", 30)
    bot = trust.get("bot_risk_score", 20)

    trust_factor = (
        (auth / 100) * 0.30
        + (natural / 100) * 0.15
        + (1 - catfish / 100) * 0.35
        + (1 - bot / 100) * 0.20
    )
    adjusted = base_overall * trust_factor
    adjusted -= catfish * 0.25
    adjusted -= bot * 0.15
    adjusted = max(0, min(100, round(adjusted, 1)))

    percolation = adjusted - (catfish * 0.6) - (bot * 0.4)
    if catfish >= 70:
        percolation -= 30
    if bot >= 65:
        percolation -= 15

    trust_note = trust.get("trust_explanation", "")
    explanation = base_scores.get("explanation", "")
    if trust_note and catfish >= 40:
        explanation = f"{trust_note} {explanation}"

    return {
        **base_scores,
        "overall_score": adjusted,
        "percolation_priority": round(percolation, 1),
        "authenticity_score": auth,
        "naturalness_score": natural,
        "catfish_risk_score": catfish,
        "bot_risk_score": bot,
        "trust_explanation": trust_note,
        "explanation": explanation.strip(),
    }