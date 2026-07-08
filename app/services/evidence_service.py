"""Add notes and message screenshots to existing profile tiles."""
import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.profile import Profile, ProfileEvidence, Ranking
from app.services import llm_service, ranking_service, trust_service
from app.services.model_router import route

logger = logging.getLogger(__name__)

NOTE_PROMPT = """The user added a private note about someone they are evaluating on a dating/social app.

PROFILE SO FAR:
{profile_json}

USER NOTE:
{note}

Return ONLY valid JSON:
{{
  "summary": "1-2 sentence synthesis of what this note adds",
  "red_flags": ["new concerns from the note"],
  "green_flags": ["positive signals from the note"],
  "structured_facts": {{"key": "value"}},
  "suggested_bio_append": "text to merge into profile bio or empty string"
}}"""

MESSAGE_SCREENSHOT_PROMPT = """This is a screenshot of messages/chat with someone the user is evaluating.

Extract conversation signals useful for trust and compatibility vetting.

Return ONLY valid JSON:
{{
  "platform": "imessage|whatsapp|tinder|bumble|hinge|facebook|other",
  "summary": "brief summary of the conversation tone and content",
  "red_flags": ["concerns"],
  "green_flags": ["positive signals"],
  "quotes": ["notable short quotes if visible"],
  "responsiveness": "high|medium|low|unknown",
  "consistency_notes": "any inconsistencies with their profile"
}}"""


def _profile_snapshot(profile: Profile) -> str:
    return json.dumps(
        {
            "name": profile.name,
            "username": profile.username,
            "bio": profile.bio,
            "platform": profile.platform,
            "location": profile.location,
            "extracted_data": profile.extracted_data,
        },
        indent=2,
    )


def _merge_note_into_profile(profile: Profile, parsed: dict) -> None:
    # Never write user notes into the subject's bio: the bio renders as THEIR
    # words on the card and feeds every future prompt as profile content.
    extracted = dict(profile.extracted_data or {})
    flags = extracted.get("user_notes") or []
    flags.append(parsed.get("summary"))
    extracted["user_notes"] = flags[-10:]
    for key in ("red_flags", "green_flags"):
        existing = extracted.get(key) or []
        extracted[key] = (existing + parsed.get(key, []))[-15:]
    profile.extracted_data = extracted


def _merge_message_into_profile(profile: Profile, parsed: dict) -> None:
    # Chat summaries stay in message_evidence (prompts already consume it) —
    # not in the subject's bio.
    extracted = dict(profile.extracted_data or {})
    msgs = extracted.get("message_evidence") or []
    msgs.append(parsed)
    extracted["message_evidence"] = msgs[-10:]
    profile.extracted_data = extracted


async def add_note(
    db: Session,
    profile: Profile,
    account_id: int,
    note: str,
    *,
    tokens_charged: int,
    analyze: bool = True,
) -> ProfileEvidence:
    """Store a private note; optionally run LLM signal extraction.

    Plain saving (analyze=False) is free and makes no model calls — paying
    tokens to jot a note is hostile for a premium product.
    """
    parsed: dict = {}
    if analyze:
        prompt = NOTE_PROMPT.format(
            profile_json=_profile_snapshot(profile), note=note
        )
        parsed, _usage = await llm_service.generate_json(prompt)
        _merge_note_into_profile(profile, parsed)
    else:
        extracted = dict(profile.extracted_data or {})
        notes_list = extracted.get("user_notes") or []
        notes_list.append(note)
        extracted["user_notes"] = notes_list[-10:]
        profile.extracted_data = extracted
    evidence = ProfileEvidence(
        profile_id=profile.id,
        account_id=account_id,
        kind="note",
        content_text=note,
        extracted_json=parsed,
        tokens_charged=tokens_charged,
    )
    db.add(evidence)
    db.flush()
    return evidence


async def add_message_screenshot(
    db: Session,
    profile: Profile,
    account_id: int,
    image_bytes: bytes,
    *,
    tokens_charged: int,
) -> ProfileEvidence:
    parsed, _usage = await llm_service.analyze_image_json(
        MESSAGE_SCREENSHOT_PROMPT, image_bytes, max_dim=1536
    )
    _merge_message_into_profile(profile, parsed)
    upload_dir = Path("data/uploads") / str(profile.id) / "evidence"
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"message_{profile.id}_{len(profile.evidence or [])}.jpg"
    path.write_bytes(image_bytes)
    evidence = ProfileEvidence(
        profile_id=profile.id,
        account_id=account_id,
        kind="message_screenshot",
        media_path=str(path),
        extracted_json=parsed,
        tokens_charged=tokens_charged,
    )
    db.add(evidence)
    db.flush()
    return evidence


async def refresh_ranking(
    db: Session,
    profile: Profile,
    preference,
    user_gender: str | None,
    user_intentions: list[str] | None,
    ui_context: dict | None,
    user_profile: dict | None = None,
    trigger: str = "Re-analysis",
) -> Ranking | None:
    ranking = db.query(Ranking).filter(Ranking.profile_id == profile.id).first()
    if not ranking:
        return None
    ranking_service.snapshot_ranking(ranking, trigger)
    trust = profile.trust_analysis or {}
    scores = await ranking_service.rank_profile(
        profile,
        preference,
        user_gender=user_gender,
        user_intentions=user_intentions,
        ui_context=ui_context,
        user_profile=user_profile,
    )
    adjusted = trust_service.compute_trust_adjusted_scores(scores, trust)
    ranking.overall_score = adjusted["overall_score"]
    ranking.compatibility_score = adjusted["compatibility_score"]
    ranking.attractiveness_score = adjusted["attractiveness_score"]
    ranking.red_flag_score = adjusted["red_flag_score"]
    ranking.percolation_priority = adjusted["percolation_priority"]
    ranking.explanation = adjusted.get("explanation")
    ranking_service.apply_feedback_percolation(ranking)
    ranking_service.apply_ranking_to_profile(profile, adjusted)
    return ranking