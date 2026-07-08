"""User onboarding: profile capture, preference vector generation, embeddings."""
import json
import logging
import re

from pathlib import Path

import httpx
from app.utils.image import save_jpeg
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.profile import PreferenceVector
from app.models.user import UserProfile
from app.services import llm_service, referral_service, vision_service
from app.utils.profile_labels import GOAL_LABELS, format_seeking, match_profile_label

logger = logging.getLogger(__name__)
settings = get_settings()

INTENTION_LABELS = GOAL_LABELS

BASE_WEIGHTS_BY_INTENT = {
    "ltr": {"compatibility": 0.50, "attractiveness": 0.20, "red_flags": 0.30},
    "marriage": {"compatibility": 0.55, "attractiveness": 0.15, "red_flags": 0.30},
    "casual": {"compatibility": 0.25, "attractiveness": 0.45, "red_flags": 0.30},
    "hookups": {"compatibility": 0.15, "attractiveness": 0.55, "red_flags": 0.30},
    "friendship": {"compatibility": 0.55, "attractiveness": 0.10, "red_flags": 0.35},
    "undecided": {"compatibility": 0.40, "attractiveness": 0.30, "red_flags": 0.30},
    "other": {"compatibility": 0.40, "attractiveness": 0.30, "red_flags": 0.30},
}

SELFIE_ANALYSIS_PROMPT = """This is a selfie of the USER (not a candidate profile).
They are a {gender} interested in {seeking} with goals: {intentions}.

Infer presentation and compatibility signals that help rank candidates FOR THIS USER.
Return ONLY valid JSON:
{{
  "presentation_style": ["how they present visually"],
  "energy_signals": ["social/romantic energy inferred"],
  "compatibility_hooks": ["what kinds of profiles likely mesh with them"],
  "visual_preferences_implied": ["taste signals from their own presentation"]
}}"""

PREFERENCE_VECTOR_PROMPT = """You are a dating preference analyst building a personalized match ranking profile.

USER PROFILE:
- Their gender: {gender}
- Interested in profiles of: {seeking}
- Dating goals: {intentions}
{identity_block}
{other_note}
{examples_block}
{selfie_block}

Based on this user's identity and goals, generate a rich preference vector for ranking dating profiles.

Return ONLY valid JSON:
{{
  "traits": {{
    "values": ["prioritized values"],
    "lifestyle": ["lifestyle fit signals"],
    "communication": ["communication style preferences"],
    "dealbreakers": ["hard no's tailored to their intentions"],
    "attraction": ["what they likely find attractive given context"],
    "interests_preferred": ["hobbies/interests to look for"],
    "intention_alignment": ["what signals match their stated goals"]
  }},
  "weights": {{
    "compatibility": 0.0-1.0,
    "attractiveness": 0.0-1.0,
    "red_flags": 0.0-1.0
  }},
  "ui_context": {{
    "tone": "supportive coaching tone for this user",
    "focus_areas": ["what to emphasize in explanations"],
    "red_flag_lens": ["intention-specific red flags to watch"],
    "conversation_style": "how to phrase openers for this user"
  }},
  "summary": "One sentence describing this user's ideal match profile"
}}

Weights must sum to 1.0. Tailor heavily:
- LTR/marriage seekers: prioritize values, emotional availability, consistency
- Casual/hookup seekers: prioritize chemistry signals, clear intentions, fun
- Friendship: de-emphasize romance, emphasize shared interests and reliability
Adapt language and priorities to the user's gender context without stereotyping."""

EXAMPLE_INFERENCE_PROMPT = """This is a dating profile screenshot the USER LIKES or finds appealing.
They are a {gender} interested in {seeking} and their goals are: {intentions}.

Analyze what this example reveals about their taste and preferences.
Return ONLY valid JSON:
{{
  "appeal_factors": ["why they might like this profile"],
  "trait_signals": ["personality/lifestyle traits inferred"],
  "visual_preferences": ["appearance/style signals if visible"],
  "values_signals": ["values this profile suggests"],
  "intention_fit": "how this aligns with their stated goals"
}}"""


def _normalize_handle(handle: str | None) -> str | None:
    if not handle:
        return None
    cleaned = handle.strip().lstrip("@").strip()
    return cleaned or None


def save_user_image(image_bytes: bytes, account_id: int, kind: str) -> str:
    """Persist avatar/selfie under data/uploads/users/<account_id>/."""
    upload_dir = Path("data/uploads/users") / str(account_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{kind}.jpg"
    save_jpeg(image_bytes, path)
    return str(path)


def user_profile_context(user: UserProfile) -> dict:
    """Structured optional identity fields for ranking and preference prompts."""
    return {
        "display_name": user.display_name,
        "handle": user.handle,
        "age": user.age,
        "location": user.location,
        "bio": user.bio,
        "has_avatar": bool(user.avatar_path),
        "has_selfie": bool(user.selfie_path),
        "selfie_analysis": user.selfie_analysis or {},
    }


def format_identity_block(user: UserProfile | None) -> str:
    if not user:
        return ""
    lines: list[str] = []
    if user.display_name:
        lines.append(f"- Name: {user.display_name}")
    if user.age:
        lines.append(f"- Age: {user.age}")
    if user.location:
        lines.append(f"- Location: {user.location}")
    if user.bio:
        lines.append(f"- About them: {user.bio}")
    if user.selfie_analysis:
        lines.append(
            "- Selfie signals: "
            + json.dumps(user.selfie_analysis, ensure_ascii=False)
        )
    if not lines:
        return ""
    return "OPTIONAL IDENTITY (user-provided — use for compatibility matching):\n" + "\n".join(
        lines
    )


def get_or_create_user(db: Session, account_id: int | None = None) -> UserProfile:
    if account_id:
        user = (
            db.query(UserProfile).filter(UserProfile.account_id == account_id).first()
        )
        if not user:
            user = UserProfile(account_id=account_id)
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    user = db.query(UserProfile).filter(UserProfile.id == 1).first()
    if not user:
        user = UserProfile(id=1)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_user_preference(
    db: Session, account_id: int | None = None
) -> PreferenceVector | None:
    if account_id:
        user = (
            db.query(UserProfile).filter(UserProfile.account_id == account_id).first()
        )
    else:
        user = db.query(UserProfile).filter(UserProfile.id == 1).first()
    if user and user.preference_vector_id:
        return (
            db.query(PreferenceVector)
            .filter(PreferenceVector.id == user.preference_vector_id)
            .first()
        )
    return (
        db.query(PreferenceVector)
        .filter(PreferenceVector.is_default.is_(True))
        .first()
    )


def _blend_weights(intentions: list[str]) -> dict:
    if not intentions:
        return BASE_WEIGHTS_BY_INTENT["undecided"].copy()
    totals = {"compatibility": 0.0, "attractiveness": 0.0, "red_flags": 0.0}
    for intent in intentions:
        w = BASE_WEIGHTS_BY_INTENT.get(intent, BASE_WEIGHTS_BY_INTENT["undecided"])
        for k in totals:
            totals[k] += w[k]
    n = len(intentions)
    return {k: round(v / n, 2) for k, v in totals.items()}


def _fallback_preference_vector(
    gender: str,
    intentions: list[str],
    preferred_genders: list[str],
    example_analyses: list[dict],
) -> dict:
    labels = [INTENTION_LABELS.get(i, i) for i in intentions]
    seeking = format_seeking(preferred_genders)
    traits_from_examples: list[str] = []
    for ex in example_analyses:
        traits_from_examples.extend(ex.get("trait_signals", []))
        traits_from_examples.extend(ex.get("appeal_factors", []))

    dealbreakers = ["dishonesty", "disrespect"]
    if "ltr" in intentions or "marriage" in intentions:
        dealbreakers.extend(["emotional unavailability", "inconsistent communication"])
    if "casual" in intentions or "hookups" in intentions:
        dealbreakers.extend(["unclear intentions", "pushiness"])

    return {
        "traits": {
            "values": ["kindness", "authenticity"],
            "lifestyle": ["compatible social energy"],
            "communication": ["clear and engaging"],
            "dealbreakers": dealbreakers,
            "attraction": traits_from_examples[:5] or ["genuine presentation"],
            "interests_preferred": [],
            "intention_alignment": labels,
            "user_gender": gender,
            "preferred_genders": preferred_genders,
            "user_intentions": intentions,
        },
        "weights": _blend_weights(intentions),
        "ui_context": {
            "tone": f"Direct, supportive coaching for a {gender} interested in {seeking}",
            "focus_areas": labels,
            "red_flag_lens": dealbreakers,
            "conversation_style": "warm and goal-aligned",
        },
        "summary": f"Match profile for {gender} interested in {seeking} — goals: {', '.join(labels)}",
    }


async def analyze_selfie(
    image_bytes: bytes,
    gender: str,
    intentions: list[str],
    preferred_genders: list[str],
) -> dict:
    labels = [INTENTION_LABELS.get(i, i) for i in intentions]
    prompt = SELFIE_ANALYSIS_PROMPT.format(
        gender=gender,
        seeking=format_seeking(preferred_genders),
        intentions=", ".join(labels),
    )
    try:
        result, _usage = await llm_service.analyze_image_json(
            prompt, image_bytes, max_dim=1024
        )
        return result
    except (json.JSONDecodeError, ValueError, Exception):
        return {"presentation_style": ["authentic presentation"], "parse_error": True}


async def analyze_liked_example(
    image_bytes: bytes,
    gender: str,
    intentions: list[str],
    preferred_genders: list[str],
) -> dict:
    labels = [INTENTION_LABELS.get(i, i) for i in intentions]
    prompt = EXAMPLE_INFERENCE_PROMPT.format(
        gender=gender,
        seeking=format_seeking(preferred_genders),
        intentions=", ".join(labels),
    )
    try:
        result, _usage = await llm_service.analyze_image_json(
            prompt, image_bytes, max_dim=1024
        )
        return result
    except (json.JSONDecodeError, ValueError, Exception):
        return {"appeal_factors": ["visual appeal"], "parse_error": True}


async def generate_preference_vector(
    gender: str,
    intentions: list[str],
    preferred_genders: list[str],
    example_analyses: list[dict],
    other_note: str | None = None,
    identity_block: str = "",
    selfie_analysis: dict | None = None,
) -> dict:
    labels = [INTENTION_LABELS.get(i, i) for i in intentions]
    examples_block = ""
    if example_analyses:
        examples_block = (
            "LIKED PROFILE EXAMPLES (user finds these appealing):\n"
            + json.dumps(example_analyses, indent=2)
        )
    selfie_block = ""
    if selfie_analysis:
        selfie_block = (
            "USER SELFIE ANALYSIS (their own presentation — calibrate compatibility):\n"
            + json.dumps(selfie_analysis, indent=2)
        )
    other = f"- Other notes: {other_note}" if other_note else ""
    prompt = PREFERENCE_VECTOR_PROMPT.format(
        gender=gender,
        seeking=format_seeking(preferred_genders),
        intentions=", ".join(labels),
        identity_block=identity_block,
        other_note=other,
        examples_block=examples_block,
        selfie_block=selfie_block,
    )
    try:
        result, _usage = await llm_service.generate_json(
            prompt, model=settings.xai_text_fast, timeout=600.0
        )
    except Exception as exc:
        logger.warning("LLM preference generation failed: %s", exc)
        result = _fallback_preference_vector(
            gender, intentions, preferred_genders, example_analyses
        )

    if "weights" not in result or not result["weights"]:
        result["weights"] = _blend_weights(intentions)
    w = result["weights"]
    total = sum(w.values()) or 1
    result["weights"] = {k: round(v / total, 2) for k, v in w.items()}

    result["traits"]["user_gender"] = gender
    result["traits"]["preferred_genders"] = preferred_genders
    result["traits"]["user_intentions"] = intentions
    if selfie_analysis:
        result["traits"]["user_selfie_signals"] = selfie_analysis
    return result


async def complete_onboarding(
    db: Session,
    gender: str,
    intentions: list[str],
    preferred_genders: list[str],
    example_images: list[bytes] | None = None,
    other_note: str | None = None,
    account_id: int | None = None,
    display_name: str | None = None,
    age: int | None = None,
    location: str | None = None,
    bio: str | None = None,
    avatar_bytes: bytes | None = None,
) -> UserProfile:
    user = get_or_create_user(db, account_id=account_id)
    example_analyses: list[dict] = []
    selfie_analysis: dict = {}

    user.display_name = (display_name or "").strip() or None
    user.handle = _normalize_handle(user.display_name)
    user.age = age
    user.location = (location or "").strip() or None
    user.bio = (bio or "").strip() or None

    media_account_id = account_id or user.id
    if avatar_bytes:
        saved = save_user_image(avatar_bytes, media_account_id, "avatar")
        user.avatar_path = saved
        user.selfie_path = saved
        selfie_analysis = await analyze_selfie(
            avatar_bytes, gender, intentions, preferred_genders
        )
        user.selfie_analysis = selfie_analysis

    if example_images:
        for img in example_images:
            analysis = await analyze_liked_example(
                img, gender, intentions, preferred_genders
            )
            example_analyses.append(analysis)

    pref_data = await generate_preference_vector(
        gender,
        intentions,
        preferred_genders,
        example_analyses,
        other_note,
        identity_block=format_identity_block(user),
        selfie_analysis=selfie_analysis or user.selfie_analysis or None,
    )

    profile_name = match_profile_label(
        gender=gender,
        preferred_genders=preferred_genders,
        goals=intentions,
    )

    if user.preference_vector_id:
        pref = (
            db.query(PreferenceVector)
            .filter(PreferenceVector.id == user.preference_vector_id)
            .first()
        )
        if pref:
            pref.name = profile_name
            pref.description = pref_data.get("summary", "")
            pref.traits = pref_data.get("traits", {})
            pref.weights = pref_data.get("weights", {})
    else:
        pref = PreferenceVector(
            name=profile_name,
            description=pref_data.get("summary", ""),
            traits=pref_data.get("traits", {}),
            weights=pref_data.get("weights", {}),
            is_default=False,
        )
        db.add(pref)
        db.flush()
        user.preference_vector_id = pref.id

    user.gender = gender
    user.preferred_genders = preferred_genders
    user.intentions = intentions
    user.example_analyses = example_analyses
    user.ui_context = pref_data.get("ui_context", {})
    was_complete = user.onboarding_complete
    user.onboarding_complete = True
    if not was_complete and user.account_id:
        referral_service.mark_onboarding_complete(db, user.account_id)
    db.commit()
    db.refresh(user)
    return user