"""Trend-aware threat intel — Grok's x_search keeps the scoring rubric current.

A scheduled job asks Grok (via its server-side ``x_search`` tool) what
romance-scam / catfish / dating-bot tactics are trending on X right now.
The structured brief is cached to disk and injected into the catfish-synthesis
and X-verification prompts, so MatchForge's scoring adapts weekly to live
tactics instead of relying on a frozen rubric.
"""
import json
import logging
import time
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)

BRIEF_PATH = Path("data/threat_brief.json")

THREAT_INTEL_PROMPT = """Search X for the last 14 days of public discussion about romance scams, \
catfishing tactics, dating-app bots, pig-butchering scripts, and stolen-photo schemes. \
Focus on what victims, security researchers, and dating-safety accounts are reporting RIGHT NOW.

Synthesize the 5-8 most prevalent current tactics.

Return ONLY valid JSON:
{
  "tactics": [
    {
      "tactic": "short name",
      "indicators": ["observable red flags in a dating profile or chat"],
      "example_phrasings": ["verbatim-style phrases scammers currently use"]
    }
  ],
  "summary": "2-3 sentence overview of the current threat landscape"
}"""

# Static seed so scoring is trend-aware even before the first live refresh
# (or on self-hosted installs without an xAI key).
SEED_BRIEF = {
    "generated_at": 0,
    "source": "seed",
    "summary": (
        "Baseline tactics: crypto 'pig butchering' romance funnels, AI-generated "
        "profile photos, off-platform pivot pressure, and military/oil-rig "
        "long-distance personas remain the dominant catfish patterns."
    ),
    "tactics": [
        {
            "tactic": "Crypto pig-butchering funnel",
            "indicators": [
                "Quick pivot to investment or trading talk",
                "Screenshots of luxury lifestyle with vague job",
                "Pushes WhatsApp/Telegram within first days",
            ],
            "example_phrasings": [
                "my uncle taught me to trade USDT",
                "I can teach you how I make passive income",
            ],
        },
        {
            "tactic": "AI-generated persona",
            "indicators": [
                "Studio-perfect photos with inconsistent backgrounds",
                "No social footprint older than a few months",
                "Bio reads generically well-written but impersonal",
            ],
            "example_phrasings": [],
        },
        {
            "tactic": "Unavailable-professional persona",
            "indicators": [
                "Deployed military, offshore rig, or overseas doctor story",
                "Can never video call",
                "Early intense affection ('love bombing')",
            ],
            "example_phrasings": [
                "the connection here is so bad, I can't video call",
                "I've never felt this way so fast",
            ],
        },
        {
            "tactic": "Verification-dodging",
            "indicators": [
                "Refuses simple realtime selfie or platform verification",
                "Photos never match claimed timeline or season",
            ],
            "example_phrasings": ["my camera is broken"],
        },
    ],
}


def _load_cached() -> dict | None:
    try:
        if BRIEF_PATH.exists():
            return json.loads(BRIEF_PATH.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Threat brief cache unreadable: %s", exc)
    return None


def get_brief() -> dict:
    """Current threat brief — live cache if present, else the static seed."""
    cached = _load_cached()
    if cached and cached.get("tactics"):
        return cached
    return SEED_BRIEF


def brief_is_stale() -> bool:
    settings = get_settings()
    cached = _load_cached()
    if not cached:
        return True
    age_days = (time.time() - float(cached.get("generated_at") or 0)) / 86400
    return age_days >= settings.threat_intel_refresh_days


def format_brief_for_prompt(brief: dict | None = None, *, max_tactics: int = 6) -> str:
    """Compact text block injected into scoring prompts."""
    brief = brief or get_brief()
    lines = [brief.get("summary", "").strip()]
    for tactic in (brief.get("tactics") or [])[:max_tactics]:
        indicators = "; ".join(tactic.get("indicators") or [])
        lines.append(f"- {tactic.get('tactic')}: {indicators}")
    return "\n".join(line for line in lines if line)


async def refresh_brief() -> dict:
    """Ask Grok (x_search) for the current scam-tactic landscape and cache it."""
    from app.services import llm_service

    settings = get_settings()
    if not settings.threat_intel_enabled or not settings.xai_api_key:
        return get_brief()

    try:
        parsed, result = await llm_service.generate_agentic_json(
            THREAT_INTEL_PROMPT,
            model=settings.xai_text_reason,
            tools=[{"type": "x_search"}, {"type": "web_search"}],
            max_turns=settings.xai_agent_max_turns,
            timeout=600.0,
        )
    except Exception as exc:
        logger.warning("Threat intel refresh failed: %s", exc)
        return get_brief()

    if not parsed.get("tactics"):
        logger.warning("Threat intel refresh returned no tactics — keeping old brief")
        return get_brief()

    brief = {
        "generated_at": time.time(),
        "source": "grok_x_search",
        "summary": parsed.get("summary", ""),
        "tactics": parsed.get("tactics", []),
        "citations": result.citations,
    }
    try:
        BRIEF_PATH.parent.mkdir(parents=True, exist_ok=True)
        BRIEF_PATH.write_text(json.dumps(brief, indent=2))
    except OSError as exc:
        logger.warning("Could not persist threat brief: %s", exc)
    logger.info(
        "Threat brief refreshed: %d tactics, %d citations",
        len(brief["tactics"]),
        len(result.citations),
    )
    return brief


async def refresh_if_stale() -> dict:
    if brief_is_stale():
        return await refresh_brief()
    return get_brief()
