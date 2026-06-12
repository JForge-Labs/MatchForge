"""Unified agent prompt — enrich profiles via text, images, and vet requests."""
import json
import logging
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.profile import Profile, ProfileEvidence, Ranking, SocialEnrichment
from app.services import (
    evidence_service,
    llm_service,
    onboarding_service,
    profile_extract_service,
    profile_merge_service,
    ranking_service,
    social_enrich_service,
    trust_service,
    vetting_service,
    vision_service,
)
from app.services.model_router import route

logger = logging.getLogger(__name__)

AGENT_PROMPT = """You are MatchForge's profile vetting agent. The user is enriching a candidate they are evaluating.

CURRENT PROFILE:
{profile_json}

USER INSTRUCTION:
{prompt}

NEW IMAGE ANALYSES (if any):
{image_summaries}

Return ONLY valid JSON:
{{
  "interpretation": "1 sentence on what the user is trying to learn or add",
  "summary": "1-2 sentence synthesis merged into profile intelligence",
  "red_flags": ["new concerns"],
  "green_flags": ["positive signals"],
  "structured_facts": {{"key": "value"}},
  "suggested_bio_append": "text to merge or empty string",
  "request_deep_vet": true/false,
  "user_vouches_real": true/false
}}

Rules:
- request_deep_vet=true only when user asks for public/social footprint, deep vet, background check, or cross-platform lookup.
- user_vouches_real=true when user explicitly says they know this person is real/human (lowers false bot positives).
- Do not invent facts not supported by profile data or user input."""

_VET_RE = re.compile(
    r"\b(deep\s*vet|vet\s+them|public\s+footprint|social\s+enrich|background\s+check|"
    r"look\s+them\s+up|linkedin|instagram|facebook|cross.?platform)\b",
    re.I,
)
def estimate_agent_cost(prompt: str, image_count: int, url_count: int = 0) -> int:
    """Rough minimum tokens for UI hint before submit."""
    cost = route("rank_refresh").token_cost
    if prompt.strip():
        cost += route("profile_agent").token_cost
    cost += route("profile_agent_image").token_cost * image_count
    cost += route("social_link").token_cost * url_count
    if prompt and _VET_RE.search(prompt):
        cost += route("deep_vet").token_cost
    return cost


_REAL_RE = re.compile(
    r"\b(know\s+them|met\s+them|real\s+person|not\s+a\s+bot|human|friend\s+of\s+mine|"
    r"i\s+know\s+her|i\s+know\s+him|verified\s+irl)\b",
    re.I,
)


def _profile_snapshot(profile: Profile) -> str:
    return json.dumps(
        {
            "name": profile.name,
            "username": profile.username,
            "bio": profile.bio,
            "platform": profile.platform,
            "location": profile.location,
            "extracted_data": profile.extracted_data,
            "trust_scores": {
                "authenticity": profile.authenticity_score,
                "catfish_risk": profile.catfish_risk_score,
                "bot_risk": profile.bot_risk_score,
            },
        },
        indent=2,
    )


def _merge_agent_result(profile: Profile, parsed: dict) -> None:
    append = (parsed.get("suggested_bio_append") or "").strip()
    if append:
        profile.bio = f"{profile.bio or ''}\n\n[Agent] {append}".strip()
    extracted = dict(profile.extracted_data or {})
    notes = extracted.get("agent_notes") or []
    if parsed.get("summary"):
        notes.append(parsed["summary"])
    extracted["agent_notes"] = notes[-12:]
    for key in ("red_flags", "green_flags"):
        existing = extracted.get(key) or []
        extracted[key] = (existing + parsed.get(key, []))[-15:]
    facts = extracted.get("structured_facts") or {}
    facts.update(parsed.get("structured_facts") or {})
    extracted["structured_facts"] = facts
    profile.extracted_data = extracted


def _apply_user_vouch(profile: Profile, parsed: dict) -> None:
    if not parsed.get("user_vouches_real"):
        return
    trust = dict(profile.trust_analysis or {})
    bot = dict(trust.get("bot_analysis") or {})
    prior = float(bot.get("bot_risk_score") or profile.bot_risk_score or 30)
    adjusted = min(prior, 22)
    bot["bot_risk_score"] = adjusted
    bot["signals"] = [s for s in bot.get("signals", []) if "generic" not in s.lower()]
    bot["explanation"] = "User vouched — bot risk discounted."
    trust["bot_analysis"] = bot
    trust["bot_risk_score"] = adjusted
    factors = [f for f in trust.get("risk_factors", []) if "bot" not in f.lower() and "generic" not in f.lower()]
    trust["risk_factors"] = factors
    profile.trust_analysis = trust
    profile.bot_risk_score = adjusted


async def _ingest_profile_screenshot(
    db: Session,
    profile: Profile,
    image_bytes: bytes,
    *,
    account_id: int,
) -> tuple[dict, str]:
    """Extract and merge a platform screenshot — trust runs once after all images."""
    analysis = await vision_service.analyze_screenshot(image_bytes)
    photo_path = vision_service.save_screenshot(
        image_bytes, profile.id, len(profile.photos or [])
    )
    profile_merge_service.merge_analysis_into_profile(
        profile,
        analysis,
        photo_path=photo_path,
        photo_index=len(profile.photos or []),
    )

    evidence = ProfileEvidence(
        profile_id=profile.id,
        account_id=account_id,
        kind="profile_screenshot",
        media_path=photo_path,
        content_text=analysis.get("platform"),
        extracted_json=analysis,
        tokens_charged=0,
    )
    db.add(evidence)
    return analysis, "profile_agent_image"


async def _finalize_profile_vetting(
    db: Session,
    profile: Profile,
    *,
    run_social_enrich: bool,
) -> list:
    """Run trust, Brave web search, and optional social enrichment once."""
    images = profile_merge_service.load_profile_photo_bytes(profile)
    if not images:
        return []

    trust = await trust_service.analyze_profile_trust(
        image_bytes_list=images,
        bio=profile.bio,
        profile_metadata=profile.extracted_data or {},
    )
    enrichments: list = []
    if run_social_enrich:
        enrichments = await social_enrich_service.enrich_profile(profile)
        for enrichment in enrichments:
            existing = (
                db.query(SocialEnrichment)
                .filter(
                    SocialEnrichment.profile_id == profile.id,
                    SocialEnrichment.platform == enrichment.platform,
                )
                .first()
            )
            if existing:
                existing.username = enrichment.username
                existing.url = enrichment.url
                existing.summary = enrichment.summary
                existing.findings = enrichment.findings
            else:
                db.add(enrichment)
        db.flush()

        if trust.get("photo_analyses"):
            catfish = await trust_service.assess_catfish_risk(
                trust["photo_analyses"], profile.bio, enrichments
            )
            trust["catfish_analysis"] = catfish
            trust["social_mismatch"] = catfish.get("social_mismatch", False)
            trust["catfish_risk_score"] = catfish.get("catfish_risk_score")
            trust["authenticity_score"] = catfish.get("authenticity_score")
            trust["consistency_score"] = catfish.get("consistency_score")
            trust["risk_factors"] = catfish.get("risk_factors", [])

    vetting = await vetting_service.vet_profile(
        name=profile.name,
        bio=profile.bio,
        location=profile.location,
        extracted_data=profile.extracted_data,
        trust_analysis=trust,
        social_enrichments=enrichments,
        run_web_search=True,
    )
    trust = vetting_service.merge_vetting_into_trust(trust, vetting)
    profile_merge_service.merge_trust_into_profile(profile, trust)
    if run_social_enrich:
        profile.enrichment_status = "done"
    return enrichments


async def _process_social_url(
    db: Session,
    profile: Profile,
    url: str,
    *,
    account_id: int,
) -> tuple[dict, str]:
    """Ingest a dropped/pasted social profile URL onto this tile."""
    parsed = profile_extract_service.parse_social_profile_url(url)
    if not parsed:
        return {"url": url, "status": "unrecognized"}, "user_note"

    platform = parsed["platform"]
    username = parsed["username"]
    if not profile.username:
        profile.username = username
    if not profile.platform or profile.platform == "other":
        profile.platform = platform

    extracted = dict(profile.extracted_data or {})
    extracted["profile_url"] = parsed["profile_url"]
    social_links = list(extracted.get("social_links") or [])
    if url not in social_links:
        social_links.append(url)
    extracted["social_links"] = social_links[-10:]
    profile.extracted_data = extracted

    findings = await social_enrich_service.search_platform(platform, username)
    summary = social_enrich_service._summarize_findings(platform, findings)
    profile_url = social_enrich_service._profile_url(
        platform, username, findings.get("search_url")
    ) or parsed["profile_url"]

    existing = (
        db.query(SocialEnrichment)
        .filter(
            SocialEnrichment.profile_id == profile.id,
            SocialEnrichment.platform == platform,
        )
        .first()
    )
    if existing:
        existing.username = username
        existing.url = profile_url
        existing.summary = summary
        existing.findings = findings
    else:
        db.add(
            SocialEnrichment(
                profile_id=profile.id,
                platform=platform,
                username=username,
                url=profile_url,
                summary=summary,
                findings=findings,
            )
        )

    profile.enrichment_status = "done"
    return {**parsed, "summary": summary, "findings_status": findings.get("status")}, "social_link"


async def _process_message_image(
    db: Session,
    profile: Profile,
    image_bytes: bytes,
    *,
    account_id: int,
) -> tuple[dict, str]:
    evidence = await evidence_service.add_message_screenshot(
        db, profile, account_id, image_bytes, tokens_charged=0
    )
    return evidence.extracted_json, "message_screenshot"


async def run_agent_prompt(
    db: Session,
    profile: Profile,
    account_id: int,
    prompt: str,
    images: list[bytes],
    urls: list[str] | None = None,
) -> dict:
    """Execute user agent instruction; return actions taken and token spend."""
    prompt = (prompt or "").strip()
    social_urls: list[str] = []
    seen_urls: set[str] = set()
    for raw in (urls or []) + profile_extract_service.extract_urls_from_text(prompt):
        url = (raw or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        social_urls.append(url)

    if not prompt and not images and not social_urls:
        return {"error": "empty", "message": "Enter a prompt, social link, or attach images."}

    tokens = 0
    charge_activities: list[str] = []
    image_summaries: list[dict] = []
    url_summaries: list[dict] = []
    actions: list[str] = []

    for url in social_urls:
        parsed, act = await _process_social_url(
            db, profile, url, account_id=account_id
        )
        actions.append("social_link")
        charge_activities.append(act)
        tokens += route(act).token_cost
        url_summaries.append(parsed if isinstance(parsed, dict) else {"url": url})

    message_mode = bool(
        prompt and re.search(r"\b(message|chat|text|conversation|dm)\b", prompt, re.I)
    )
    profile_images: list[bytes] = []

    for img in images:
        if message_mode:
            parsed, act = await _process_message_image(
                db, profile, img, account_id=account_id
            )
            actions.append("message_screenshot")
            charge_activities.append("message_screenshot")
        else:
            parsed, act = await _ingest_profile_screenshot(
                db, profile, img, account_id=account_id
            )
            profile_images.append(img)
            actions.append("profile_screenshot")
            charge_activities.append("profile_agent_image")
        tokens += route(act).token_cost
        image_summaries.append(parsed if isinstance(parsed, dict) else {"summary": str(parsed)})

    parsed_agent: dict = {}
    if prompt:
        agent_prompt = AGENT_PROMPT.format(
            profile_json=_profile_snapshot(profile),
            prompt=prompt,
            image_summaries=json.dumps(
                {"images": image_summaries, "social_links": url_summaries},
                indent=2,
            )
            or "(none)",
        )
        parsed_agent, _usage = await llm_service.generate_json(agent_prompt)
        _merge_agent_result(profile, parsed_agent)
        if _REAL_RE.search(prompt):
            parsed_agent["user_vouches_real"] = True
        _apply_user_vouch(profile, parsed_agent)
        charge_activities.append("profile_agent")
        tokens += route("profile_agent").token_cost
        actions.append("agent_prompt")

    want_vet = bool(parsed_agent.get("request_deep_vet")) or (
        prompt and _VET_RE.search(prompt)
    ) or bool(profile_images)
    enrichment_ran_inline = False

    if profile_images:
        charge_activities.append("deep_vet")
        tokens += route("deep_vet").token_cost
        await _finalize_profile_vetting(
            db, profile, run_social_enrich=want_vet
        )
        enrichment_ran_inline = want_vet
        actions.append("profile_vet_complete" if want_vet else "profile_trust_complete")

    if want_vet and not enrichment_ran_inline:
        charge_activities.append("deep_vet")
        tokens += route("deep_vet").token_cost
        actions.append("deep_vet_queued")
        profile.enrichment_status = "queued"

    if actions:
        charge_activities.append("rank_refresh")
        tokens += route("rank_refresh").token_cost
        actions.append("rank_refresh")

    evidence = ProfileEvidence(
        profile_id=profile.id,
        account_id=account_id,
        kind="agent",
        content_text=prompt[:2000] if prompt else None,
        extracted_json={
            "interpretation": parsed_agent.get("interpretation"),
            "summary": parsed_agent.get("summary"),
            "actions": actions,
            "image_count": len(images),
            "url_count": len(social_urls),
        },
        tokens_charged=tokens,
    )
    db.add(evidence)
    db.flush()

    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    pref = onboarding_service.get_user_preference(db, account_id=account_id)
    if pref:
        await evidence_service.refresh_ranking(
            db,
            profile,
            pref,
            user_gender=user.gender,
            user_intentions=user.intentions,
            ui_context=user.ui_context,
            user_profile=onboarding_service.user_profile_context(user),
        )
        ranking = db.query(Ranking).filter(Ranking.profile_id == profile.id).first()
        if ranking and profile.trust_analysis:
            ranking.bot_risk_score = profile.bot_risk_score
            ranking.trust_explanation = profile.trust_analysis.get("trust_explanation")

    from app.utils.profile_tokens import profile_tokens_spent

    return {
        "status": "ok",
        "profile_id": profile.id,
        "actions": actions,
        "charge_activities": charge_activities,
        "tokens_charged": tokens,
        "tokens_spent_total": profile_tokens_spent(profile, db),
        "interpretation": parsed_agent.get("interpretation"),
        "summary": parsed_agent.get("summary"),
        "request_deep_vet": want_vet and not enrichment_ran_inline,
        "enrichment_status": profile.enrichment_status,
        "vetting_complete": enrichment_ran_inline,
    }