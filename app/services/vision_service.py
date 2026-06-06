"""Screenshot vision analysis via local Ollama."""
import base64
import json
import logging
import re
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

VISION_PROMPT = """Analyze this dating app profile screenshot. Extract all visible information.

Return ONLY valid JSON with this structure:
{
  "name": "display name or null",
  "username": "handle/username or null",
  "age": 25 or null,
  "bio": "full bio text or null",
  "location": "city/area or null",
  "platform": "tinder|bumble|hinge|okcupid|other",
  "prompts": ["any profile prompts and answers"],
  "interests": ["listed interests/hobbies"],
  "photos_description": "brief description of visible photos",
  "red_flags": ["potential concerns visible in profile"],
  "green_flags": ["positive signals visible in profile"],
  "attractiveness_notes": "subjective appearance notes from photos if visible",
  "confidence": 0.0 to 1.0
}

Be thorough but factual. Only include what is actually visible in the screenshot."""

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
    """Resize and base64-encode an image for Ollama vision models."""
    img = Image.open(BytesIO(image_bytes))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _parse_json_response(text: str) -> dict:
    """Extract JSON from model output, tolerating markdown fences."""
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


async def _vision_analyze(prompt: str, image_bytes: bytes) -> dict:
    """Run a vision prompt against a single image."""
    b64 = _encode_image(image_bytes)
    payload = {
        "model": settings.vision_model,
        "prompt": prompt,
        "images": [b64],
        "stream": False,
        "format": "json",
    }
    async with httpx.AsyncClient(timeout=900.0) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/generate", json=payload
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "{}")
    return _parse_json_response(raw)


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

    photo_analyses: list[dict] = []
    for img in profile_images:
        auth = await analyze_authenticity(img)
        filters = await detect_filters_and_edits(img)
        photo_analyses.append({**auth, **filters})
    return await synthesize(photo_analyses, bio_text, [])


async def analyze_screenshot(
    image_bytes: bytes, user_context: dict | None = None
) -> dict:
    """Run vision model on a single screenshot; returns extracted profile data."""
    try:
        return await _vision_analyze(_build_vision_prompt(user_context), image_bytes)
    except (json.JSONDecodeError, ValueError, httpx.HTTPError) as exc:
        logger.warning("Vision JSON parse failed: %s", exc)
        return {
            "name": None,
            "username": None,
            "bio": "",
            "platform": "other",
            "confidence": 0.3,
            "parse_error": str(exc),
        }


def save_screenshot(image_bytes: bytes, profile_id: int, index: int) -> str:
    """Persist screenshot to data/uploads and return relative path."""
    upload_dir = Path("data/uploads") / str(profile_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"screenshot_{index}.jpg"
    img = Image.open(BytesIO(image_bytes))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.save(path, format="JPEG", quality=90)
    return str(path)