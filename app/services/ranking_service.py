"""AI ranking engine with customizable preference vectors."""
import json
import logging
import re

from app.core.config import get_settings
from app.models.profile import PreferenceVector, Profile, Ranking
from app.services import llm_service
from app.utils.legal import append_ai_disclaimer

logger = logging.getLogger(__name__)
settings = get_settings()

RANKING_PROMPT_TEMPLATE = """You are a personalized dating profile analyst for MatchForge.

USER IDENTITY:
- Gender: {user_gender}
- Dating intentions: {user_intentions}
{user_profile_block}

USER PREFERENCE VECTOR (generated from their onboarding + liked examples):
{preferences}

PERSONALIZATION CONTEXT:
{ui_context}

PROFILE TO EVALUATE:
{profile_data}

Score this candidate FOR THIS SPECIFIC USER — not generically.
Score pure fit only: trust/authenticity is assessed by a separate system and
applied afterward, so do NOT penalize for suspected catfishing, bots, or filters here.
ACCURACY: Only cite employers, jobs, and lifestyle facts explicitly present in PROFILE TO EVALUATE (bio, work, employer, prompts, vision_analysis). Never infer occupation or business ownership from display names or usernames alone.
Interpret each dimension per their intentions:
- LTR/marriage: values alignment and emotional availability matter most
- Casual/hookups: chemistry and clear intentions matter most
- Friendship: shared interests and reliability matter most

Return ONLY valid JSON:
{{
  "compatibility_score": 0-100,
  "attractiveness_score": 0-100,
  "red_flag_score": 0-100 (higher = more red flags FOR THIS USER),
  "explanation": "2-3 sentences tailored to this user's goals and gender context",
  "conversation_starters": ["3 openers matching their style and intentions"],
  "key_strengths": ["top 3 strengths for THIS user"],
  "key_concerns": ["concerns specific to their intentions"]
}}

Do NOT return an overall score — it is computed deterministically from the
user's own weights. Use the user's ui_context tone in explanations."""

DEFAULT_WEIGHTS = {"compatibility": 0.4, "attractiveness": 0.3, "red_flags": 0.3}


def compute_fit_score(scores: dict, weights: dict | None) -> float:
    """Deterministic weighted fit — the user's weights, verifiably applied.

    fit = compatibility·w_c + attractiveness·w_a + (100 − red_flags)·w_r,
    with weights renormalized so they always sum to 1.
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    total = (
        w.get("compatibility", 0) + w.get("attractiveness", 0) + w.get("red_flags", 0)
    )
    if total <= 0:
        w, total = dict(DEFAULT_WEIGHTS), 1.0
    compat = llm_service.clamp_score(scores.get("compatibility_score"))
    attract = llm_service.clamp_score(scores.get("attractiveness_score"))
    red = llm_service.clamp_score(scores.get("red_flag_score"))
    fit = (
        (compat if compat is not None else 50) * w.get("compatibility", 0)
        + (attract if attract is not None else 50) * w.get("attractiveness", 0)
        + (100 - (red if red is not None else 50)) * w.get("red_flags", 0)
    ) / total
    return round(max(0.0, min(100.0, fit)), 1)


def apply_feedback_percolation(ranking: Ranking) -> None:
    """Re-apply explicit user feedback after any recompute.

    Without this, re-analysis (new screenshot, note, deep vet) silently buries
    a superliked match — the app must never forget what the user told it.
    """
    if ranking.feedback == "superlike":
        ranking.percolation_priority = 999.0
    elif ranking.feedback == "like":
        ranking.percolation_priority = (ranking.overall_score or 0) + 20
    elif ranking.feedback == "dislike":
        ranking.percolation_priority = (ranking.overall_score or 0) - 50


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


def _fallback_scores(profile: Profile, pref: PreferenceVector) -> dict:
    """Heuristic scoring when LLM is unavailable."""
    green = len(profile.vision_analysis.get("green_flags", []))
    red = len(profile.vision_analysis.get("red_flags", []))
    confidence = profile.vision_analysis.get("confidence", 0.5)

    compatibility = min(100, 50 + green * 8 - red * 10)
    attractiveness = min(100, 55 + confidence * 30)
    red_flag = min(100, red * 15)
    scores = {
        "compatibility_score": round(compatibility, 1),
        "attractiveness_score": round(attractiveness, 1),
        "red_flag_score": round(red_flag, 1),
    }
    return {
        **scores,
        "overall_score": compute_fit_score(scores, pref.weights),
        "explanation": append_ai_disclaimer(
            f"Heuristic score: {green} green flags, {red} red flags detected. "
            "LLM ranking unavailable — using rule-based fallback."
        ),
        "conversation_starters": [],
        "key_strengths": profile.vision_analysis.get("green_flags", [])[:3],
        "key_concerns": profile.vision_analysis.get("red_flags", [])[:3],
    }


async def rank_profile(
    profile: Profile,
    preference: PreferenceVector,
    user_gender: str | None = None,
    user_intentions: list[str] | None = None,
    ui_context: dict | None = None,
    user_profile: dict | None = None,
) -> dict:
    """Score pure fit via LLM sub-scores; overall is computed deterministically.

    Trust is intentionally NOT given to the model — it modulates the final
    score exactly once, in trust_service.compute_trust_adjusted_scores.
    """
    traits = preference.traits or {}
    profile_block = ""
    if user_profile:
        profile_block = (
            "- Optional profile details: "
            + json.dumps(user_profile, indent=2, ensure_ascii=False)
        )
    profile_data = {
        "name": profile.name,
        "username": profile.username,
        "age": profile.age,
        "bio": profile.bio,
        "location": profile.location,
        "platform": profile.platform,
        "vision_analysis": profile.vision_analysis,
        "extracted_data": profile.extracted_data,
    }
    prompt = RANKING_PROMPT_TEMPLATE.format(
        user_gender=user_gender or traits.get("user_gender", "unspecified"),
        user_intentions=", ".join(
            user_intentions or traits.get("user_intentions", ["undecided"])
        ),
        user_profile_block=profile_block,
        preferences=json.dumps(
            {"traits": preference.traits, "weights": preference.weights}, indent=2
        ),
        ui_context=json.dumps(ui_context or {}, indent=2),
        profile_data=json.dumps(profile_data, indent=2),
    )
    try:
        result, _usage = await llm_service.generate_json(
            prompt, model=settings.xai_text_fast, timeout=600.0, temperature=0.0
        )
        for key in ("compatibility_score", "attractiveness_score", "red_flag_score"):
            clamped = llm_service.clamp_score(result.get(key))
            result[key] = clamped if clamped is not None else 50.0
        result["overall_score"] = compute_fit_score(result, preference.weights)
        if result.get("explanation"):
            result["explanation"] = append_ai_disclaimer(result["explanation"])
        return result
    except Exception as exc:
        logger.warning("LLM ranking failed for profile %s: %s", profile.id, exc)
        return _fallback_scores(profile, preference)


def compute_percolation_priority(ranking: Ranking) -> float:
    """Higher = surfaces to top of shortlist. User overrides win."""
    if ranking.user_override_rank is not None:
        return 1000.0 - ranking.user_override_rank
    return ranking.overall_score


def apply_ranking_to_profile(profile: Profile, scores: dict) -> None:
    profile.compatibility_score = scores.get("compatibility_score")
    profile.attractiveness_score = scores.get("attractiveness_score")
    profile.red_flag_score = scores.get("red_flag_score")
    profile.overall_score = scores.get("overall_score")
    profile.authenticity_score = scores.get("authenticity_score")
    profile.naturalness_score = scores.get("naturalness_score")
    profile.catfish_risk_score = scores.get("catfish_risk_score")
    profile.bot_risk_score = scores.get("bot_risk_score")
    profile.status = "ranked"