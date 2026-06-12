"""Screenshot vision analysis via xAI Grok."""
import json
import logging
from pathlib import Path

import httpx
from app.utils.image import save_jpeg

from app.services import llm_service

logger = logging.getLogger(__name__)

VISION_PROMPT = """Analyze this screenshot of a person's profile. It may be a dating app OR a social network (Facebook, Instagram, LinkedIn, X/Twitter, TikTok, etc.).

Extract ALL visible text and identity signals. Read carefully — usernames and URLs are often in small header text, browser address bars, or link previews.

Return ONLY valid JSON:
{
  "name": "display name as shown or null",
  "username": "handle, vanity username, or profile slug (e.g. from facebook.com/jane.doe → jane.doe) or null",
  "profile_url": "full profile URL if visible (browser bar, share link, m.facebook.com/...) or null",
  "age": 25 or null,
  "bio": "About/bio/intro text or null",
  "location": "city/area/live location or null",
  "hometown": "hometown if shown or null",
  "employer": "company/organization name ONLY if explicitly shown in Work/Employer/Company field — null otherwise",
  "job_title": "job title ONLY if explicitly shown — null otherwise",
  "work": "verbatim Work/Employer line from profile if shown, else null (do NOT guess from name)",
  "education": "school/university if shown or null",
  "platform": "tinder|bumble|hinge|okcupid|facebook|instagram|linkedin|x|tiktok|other",
  "prompts": ["other visible profile fields or prompt Q&A"],
  "interests": ["listed interests/hobbies"],
  "photos_description": "brief description of visible photos",
  "red_flags": ["potential concerns visible in profile"],
  "green_flags": ["positive signals visible in profile"],
  "attractiveness_notes": "subjective appearance notes from photos if visible",
  "confidence": 0.0 to 1.0
}

For Facebook specifically:
- platform must be "facebook"
- Read the browser URL bar if visible: facebook.com/USERNAME or m.facebook.com/USERNAME → put USERNAME in username
- The large name at top is "name"; the vanity slug in URLs is "username" (they differ)
- Capture About, Intro, Work, Education, Places lived, Relationship status into bio/prompts/work/education/hometown
- Do NOT return the literal string "unknown" — use null when not visible

ACCURACY RULES (critical):
- Display names and usernames are identifiers only — NEVER infer profession, business ownership, or employer from a name or handle alone (e.g. name "Lashes" does NOT imply a lash business unless Work/Employer explicitly says so).
- employer, job_title, and work must come ONLY from labeled Work/Employer/Company/Job fields visible on screen — use their exact wording. If not shown, use null.
- Do not invent employers, side businesses, or careers from wordplay on names, nicknames, or usernames.
- red_flags and green_flags must cite visible profile text or photos — not name-based assumptions.
- When both a nickname and a formal employer appear, report the employer field verbatim; do not replace it with a name-based guess.

Be thorough but factual. Only include what is actually visible."""

AUTHENTICITY_PROMPT = """Analyze this dating profile photo for authenticity and catfish signals.

Look for: AI-generated faces (uncanny smoothness, odd backgrounds, synthetic skin),
deepfakes, stolen/stock photos, inconsistent lighting, impossible anatomy,
overly perfect features, watermark remnants, celebrity lookalikes.

Return ONLY valid JSON:
{
  "authenticity_score": 0-100 (higher = more likely a real, unmanipulated person),
  "ai_generated_likelihood": 0-100 (higher = more likely AI-generated),
  "real_photo_confidence": 0-100,
  "visual_red_flags": ["specific authenticity concerns"],
  "positive_trust_signals": ["signals suggesting genuine photo"],
  "explanation": "1-2 sentence authenticity assessment"
}"""

TRUST_PHOTO_PROMPT = """Analyze this dating profile photo for authenticity, filters, and editing in one pass.

Look for AI-generated faces, deepfakes, stolen photos, beauty filters, skin smoothing,
FaceApp effects, body reshaping, and heavy enhancement.

Return ONLY valid JSON:
{
  "authenticity_score": 0-100 (higher = more likely a real, unmanipulated person),
  "ai_generated_likelihood": 0-100 (higher = more likely AI-generated),
  "real_photo_confidence": 0-100,
  "naturalness_score": 0-100 (higher = more natural, minimal editing),
  "filter_heaviness": 0-100 (higher = heavier filtering/editing detected),
  "visual_red_flags": ["specific authenticity or editing concerns"],
  "positive_trust_signals": ["signals suggesting genuine photo"],
  "editing_tools_detected": ["specific tools or effects suspected"],
  "edit_regions": ["face", "body", "background", etc.],
  "explanation": "1-2 sentence combined authenticity and editing assessment"
}"""

FILTER_DETECTION_PROMPT = """Analyze this dating profile photo for filters, editing, and enhancement.

Look for: beauty filters, skin smoothing, FaceApp effects, body reshaping,
excessive blur on skin, unnatural eye enlargement, jaw slimming,
AI enhancers, heavy makeup filters masking features, background replacement.

Return ONLY valid JSON:
{
  "naturalness_score": 0-100 (higher = more natural, minimal editing),
  "filter_heaviness": 0-100 (higher = heavier filtering/editing detected),
  "editing_tools_detected": ["specific tools or effects suspected"],
  "edit_regions": ["face", "body", "background", etc.],
  "explanation": "1-2 sentence filter/editing assessment"
}"""


def _encode_image(image_bytes: bytes, max_dim: int = 1024) -> str:
    """Backward-compatible helper for onboarding image encoding."""
    return llm_service.encode_image_jpeg(image_bytes, max_dim=max_dim).split(",", 1)[1]


def _build_vision_prompt(user_context: dict | None = None) -> str:
    if not user_context:
        return VISION_PROMPT
    gender = user_context.get("gender", "unspecified")
    intentions = ", ".join(user_context.get("intentions", ["undecided"]))
    return (
        VISION_PROMPT
        + f"\n\nCONTEXT: The viewer is a {gender} seeking {intentions}. "
        "Flag red/green signals relative to their goals."
    )


async def _vision_analyze(
    prompt: str, image_bytes: bytes, max_dim: int = 1024
) -> dict:
    result, _usage = await llm_service.analyze_image_json(
        prompt, image_bytes, max_dim=max_dim
    )
    return result


async def analyze_photo_trust(image_bytes: bytes) -> dict:
    """Single vision call for authenticity + filter/editing signals."""
    try:
        return await _vision_analyze(TRUST_PHOTO_PROMPT, image_bytes)
    except Exception as exc:
        logger.warning("Combined photo trust analysis failed: %s", exc)
        return {
            "authenticity_score": 50,
            "ai_generated_likelihood": 30,
            "real_photo_confidence": 50,
            "naturalness_score": 60,
            "filter_heaviness": 25,
            "visual_red_flags": [],
            "positive_trust_signals": [],
            "editing_tools_detected": [],
            "edit_regions": [],
            "explanation": "Photo trust check unavailable.",
        }


async def analyze_authenticity(image_bytes: bytes) -> dict:
    """Vision analysis for AI-generated vs real photos."""
    try:
        return await _vision_analyze(AUTHENTICITY_PROMPT, image_bytes)
    except Exception as exc:
        logger.warning("Authenticity analysis failed: %s", exc)
        return {
            "authenticity_score": 50,
            "ai_generated_likelihood": 30,
            "real_photo_confidence": 50,
            "visual_red_flags": [],
            "positive_trust_signals": [],
            "explanation": "Authenticity check unavailable.",
        }


async def detect_filters_and_edits(image_bytes: bytes) -> dict:
    """Detect beauty filters, skin smoothing, and heavy editing."""
    try:
        return await _vision_analyze(FILTER_DETECTION_PROMPT, image_bytes)
    except Exception as exc:
        logger.warning("Filter detection failed: %s", exc)
        return {
            "naturalness_score": 60,
            "filter_heaviness": 25,
            "editing_tools_detected": [],
            "edit_regions": [],
            "explanation": "Filter detection unavailable.",
        }


async def assess_catfish_risk(
    profile_images: list[bytes], bio_text: str | None = None
) -> dict:
    """Per-photo trust analysis aggregated for catfish risk (vision-only)."""
    from app.services.trust_service import assess_catfish_risk as synthesize

    import asyncio

    photo_analyses = list(
        await asyncio.gather(*[analyze_photo_trust(img) for img in profile_images])
    )
    return await synthesize(photo_analyses, bio_text, [])


async def analyze_screenshot(
    image_bytes: bytes, user_context: dict | None = None
) -> dict:
    """Run vision model on a single screenshot; returns extracted profile data."""
    from app.services.profile_extract_service import (
        enrich_extracted_profile,
        normalize_extracted_profile,
    )

    try:
        raw = await _vision_analyze(
            _build_vision_prompt(user_context), image_bytes, max_dim=1536
        )
        normalized = normalize_extracted_profile(raw)
        return await enrich_extracted_profile(normalized)
    except (json.JSONDecodeError, ValueError, httpx.HTTPError) as exc:
        logger.warning("Vision JSON parse failed: %s", exc)
        return normalize_extracted_profile({
            "name": None,
            "username": None,
            "bio": "",
            "platform": "other",
            "confidence": 0.3,
            "parse_error": str(exc),
        })


def save_screenshot(image_bytes: bytes, profile_id: int, index: int) -> str:
    """Persist screenshot to data/uploads and return relative path."""
    upload_dir = Path("data/uploads") / str(profile_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"screenshot_{index}.jpg"
    save_jpeg(image_bytes, path)
    return str(path)