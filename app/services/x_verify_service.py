"""X verification orchestrator — agentic Grok cross-examination of a match.

Pipeline (the EXhibit showcase flow):
  1. Official X API v2 ground truth (``x_api_service``): user lookup, timeline,
     deterministic social-proof signals. Cached; optional (graceful fallback).
  2. Grok agentic run with server-side ``x_search`` + ``web_search`` tools:
     autonomously cross-references dating-profile claims against public X
     activity, hunts current scam patterns, and cites its evidence.
  3. Vision photo cross-check: X profile image vs. dating screenshot photos.
  4. Scores blend 50/50: deterministic Python signals + Grok's judgment →
     the X Social Proof Score (fifth trust dimension).

Privacy: public X data only, fetched on explicit user action, deleted with
the profile. No DMs, no scraping — official API + Grok tools only.
"""
import json
import logging

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.profile import Profile, ProfileEvidence, Ranking, SocialEnrichment
from app.services import (
    llm_service,
    profile_merge_service,
    threat_intel_service,
    vetting_service,
    x_api_service,
)

logger = logging.getLogger(__name__)

X_VERIFY_PROMPT = """You are MatchForge's verification agent. A user matched with this person on {platform} \
and wants to know if they are who they claim to be. Investigate their public X (Twitter) footprint.

CLAIMED IDENTITY (extracted from dating profile screenshots):
{claims_json}

X ACCOUNT GROUND TRUTH (official X API — deterministic facts):
{x_api_facts_json}

RECENT X POSTS (sample):
{timeline_sample}

CURRENT SCAM TACTICS TRENDING ON X (auto-updated threat brief):
{threat_brief}

Investigate using X search and web search. Steps you may take:
1. Confirm the X account @{handle} plausibly belongs to the same person \
(name, photo description, location, interests, timeline consistency).
2. Cross-check each dating-profile claim against X evidence; mark each \
supported / contradicted / unverifiable.
3. Look for red flags: recycled scam scripts matching the threat brief, \
engagement-pod or bot-like behavior, sudden persona changes (name/handle/avatar), \
reports of impersonation or stolen photos mentioning this handle.
4. Look for green flags: years of consistent human activity, real-world event \
posts, reciprocal interactions with real friends, location-consistent content.

Rules:
- Judge only from public evidence you can actually find; never invent facts.
- "unverifiable" is a valid and common outcome — absence of evidence is weak signal.
- Keep every field concise and user-facing.

Return ONLY valid JSON:
{{
  "verdict": "verified|likely_real|inconclusive|suspicious|high_risk",
  "handle_match_confidence": 0-100,
  "x_social_proof_score": 0-100,
  "claim_checks": [
    {{"claim": "...", "status": "supported|contradicted|unverifiable", "evidence": "..."}}
  ],
  "red_flags": ["..."],
  "green_flags": ["..."],
  "confidence": 0-100,
  "one_line_summary": "single sentence a user can act on"
}}"""

PHOTO_CROSS_CHECK_PROMPT = """The FIRST image is this person's X (Twitter) profile photo. \
The remaining image(s) are photos from their dating profile.

Compare them for identity consistency.

Return ONLY valid JSON:
{
  "same_person_likelihood": 0-100,
  "identical_photo": true/false,
  "different_person_red_flag": true/false,
  "notes": "1-2 sentences on similarities/differences (face, age, style, setting)"
}"""

VERIFICATION_QUESTIONS_PROMPT = """You help a dating-app user safely verify a match is the real owner of X account @{handle}.

X ACCOUNT: {x_facts}

RECENT PUBLIC POSTS:
{timeline_sample}

Generate 3 natural, non-creepy questions the user could casually ask the match in chat. \
Each must be something ONLY the real account owner could answer confidently, grounded in \
their public X activity — but phrased so it doesn't reveal the user researched them \
(e.g. tied to interests, events, or opinions they posted about).

Rules:
- Never quote a post verbatim or mention X/Twitter in the question.
- Keep questions light and date-appropriate.
- Skip anything sensitive (health, family drama, politics they may regret).

Return ONLY valid JSON:
{{
  "questions": [
    {{
      "question": "what to ask",
      "expected_signal": "what a genuine answer would sound like, per their posts",
      "why_it_works": "1 sentence"
    }}
  ]
}}"""


def _build_claims(profile: Profile) -> dict:
    extracted = profile.extracted_data or {}
    claims = {
        "name": profile.name,
        "age": profile.age,
        "location": profile.location,
        "bio": (profile.bio or "")[:800] or None,
        "platform": profile.platform,
        "work": extracted.get("work") or extracted.get("employer"),
        "education": extracted.get("education"),
        "interests": (extracted.get("interests") or [])[:8],
        "photos_description": extracted.get("photos_description"),
    }
    return {k: v for k, v in claims.items() if v}


def _timeline_sample(timeline: list[dict], *, limit: int = 20) -> str:
    if not timeline:
        return "(no recent public posts available)"
    lines = []
    for post in timeline[:limit]:
        text = (post.get("text") or "").replace("\n", " ").strip()[:200]
        created = post.get("created_at", "")[:10]
        lines.append(f"[{created}] {text}")
    return "\n".join(lines)


def _x_facts_for_prompt(x_data: dict) -> dict:
    """Compact official-API facts block for the agent prompt."""
    if x_data.get("status") != "ok":
        return {"available": False, "reason": x_data.get("status")}
    user = x_data.get("user") or {}
    signals = x_data.get("signals") or {}
    return {
        "available": True,
        "handle": x_data.get("username"),
        "display_name": user.get("name"),
        "bio": user.get("description"),
        "location": user.get("location"),
        "created_at": user.get("created_at"),
        "verified": user.get("verified"),
        "protected": user.get("protected"),
        "public_metrics": user.get("public_metrics"),
        "deterministic_signals": signals.get("signals"),
        "deterministic_score": signals.get("deterministic_score"),
    }


def blend_social_proof(
    grok_score: float | None, deterministic_score: float | None
) -> float | None:
    """50/50 blend of Grok's qualitative judgment and Python-computed signals."""
    scores = [s for s in (grok_score, deterministic_score) if s is not None]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 1)


def _fallback_report(handle: str, x_data: dict, detail: str) -> dict:
    signals = x_data.get("signals") or {}
    return {
        "verdict": "inconclusive",
        "handle_match_confidence": None,
        "x_social_proof_score": signals.get("deterministic_score"),
        "claim_checks": [],
        "red_flags": [],
        "green_flags": signals.get("signals", [])[:5],
        "confidence": 25,
        "one_line_summary": f"Automated agent unavailable ({detail}) — showing X account facts only.",
    }


async def _photo_cross_check(profile: Profile, x_data: dict) -> dict | None:
    """Vision check: X profile image vs. dating-profile photos."""
    if x_data.get("status") != "ok":
        return None
    x_image = await x_api_service.fetch_profile_image(x_data.get("user") or {})
    if not x_image:
        return None
    profile_photos = profile_merge_service.load_profile_photo_bytes(profile)
    if not profile_photos:
        return None
    try:
        result, _usage = await llm_service.analyze_images_json(
            PHOTO_CROSS_CHECK_PROMPT,
            [x_image] + profile_photos[:2],
            timeout=300.0,
        )
        return result
    except Exception as exc:
        logger.warning("Photo cross-check failed: %s", exc)
        return None


async def run_x_verification(
    db: Session,
    profile: Profile,
    account_id: int,
    handle: str,
) -> dict:
    """Full X verification: API facts + agentic Grok investigation + photo check."""
    settings = get_settings()
    normalized = x_api_service.normalize_handle(handle)
    if not normalized:
        return {"status": "error", "message": "That doesn't look like a valid X handle."}

    # 1. Official API ground truth (cached, optional)
    x_data = await x_api_service.fetch_x_profile(db, normalized)
    signals = x_data.get("signals") or {}
    deterministic = signals.get("deterministic_score")

    # 2. Agentic Grok investigation (x_search + web_search server-side tools)
    prompt = X_VERIFY_PROMPT.format(
        platform=profile.platform or "a dating app",
        claims_json=json.dumps(_build_claims(profile), indent=2),
        x_api_facts_json=json.dumps(_x_facts_for_prompt(x_data), indent=2),
        timeline_sample=_timeline_sample(x_data.get("timeline") or []),
        threat_brief=threat_intel_service.format_brief_for_prompt(),
        handle=normalized,
    )
    citations: list[str] = []
    tool_trace: list[dict] = []
    try:
        parsed, agentic = await llm_service.generate_agentic_json(
            prompt,
            model=settings.xai_text_reason,
            tools=[{"type": "x_search"}, {"type": "web_search"}],
            max_turns=settings.xai_agent_max_turns,
            timeout=600.0,
        )
        citations = agentic.citations
        tool_trace = agentic.tool_trace
    except Exception as exc:
        logger.warning("X verification agent failed for @%s: %s", normalized, exc)
        parsed = _fallback_report(normalized, x_data, str(exc)[:120])

    # 3. Photo cross-check (vision, only when both images exist)
    photo_check = await _photo_cross_check(profile, x_data)

    # 4. Blend deterministic + qualitative into the X Social Proof Score
    grok_score = parsed.get("x_social_proof_score")
    blended = blend_social_proof(
        float(grok_score) if grok_score is not None else None,
        float(deterministic) if deterministic is not None else None,
    )
    if photo_check and photo_check.get("different_person_red_flag") and blended is not None:
        blended = max(0.0, round(blended - 25, 1))
        parsed.setdefault("red_flags", []).append(
            "X profile photo does not appear to match dating-profile photos"
        )

    report = {
        "handle": normalized,
        "profile_url": f"https://x.com/{normalized}",
        "x_api_status": x_data.get("status"),
        "verdict": parsed.get("verdict", "inconclusive"),
        "x_social_proof_score": blended,
        "grok_score": grok_score,
        "deterministic_score": deterministic,
        "deterministic_signals": signals.get("signals", []),
        "account_facts": _x_facts_for_prompt(x_data),
        "claim_checks": parsed.get("claim_checks", []),
        "red_flags": parsed.get("red_flags", []),
        "green_flags": parsed.get("green_flags", []),
        "handle_match_confidence": parsed.get("handle_match_confidence"),
        "confidence": parsed.get("confidence"),
        "one_line_summary": parsed.get("one_line_summary", ""),
        "photo_cross_check": photo_check,
        "citations": citations,
        "agent_trace": tool_trace,
        "threat_brief_source": threat_intel_service.get_brief().get("source"),
    }

    _persist_verification(db, profile, account_id, report)
    return {"status": "ok", "report": report}


def _persist_verification(
    db: Session, profile: Profile, account_id: int, report: dict
) -> None:
    """Store report, update trust scores/ranking, record evidence + enrichment."""
    handle = report["handle"]
    profile.x_verification = report
    profile.x_social_proof_score = report.get("x_social_proof_score")
    if not profile.username:
        profile.username = handle
    if not profile.platform or profile.platform == "other":
        profile.platform = "x"

    extracted = dict(profile.extracted_data or {})
    extracted["x_handle"] = handle
    for key in ("red_flags", "green_flags"):
        existing = extracted.get(key) or []
        merged = existing + [f for f in report.get(key, []) if f not in existing]
        extracted[key] = merged[-15:]
    profile.extracted_data = extracted

    # Trust integration — X social proof becomes the fifth trust dimension
    trust = dict(profile.trust_analysis or {})
    trust["x_verification"] = {
        "handle": handle,
        "verdict": report["verdict"],
        "x_social_proof_score": report.get("x_social_proof_score"),
        "one_line_summary": report.get("one_line_summary"),
    }
    trust["x_social_proof_score"] = report.get("x_social_proof_score")
    if report.get("red_flags"):
        factors = list(trust.get("risk_factors") or [])
        for flag in report["red_flags"]:
            if flag not in factors:
                factors.append(flag)
        trust["risk_factors"] = factors[-10:]
    summary = vetting_service.compute_trust_summary(
        {**trust,
         "authenticity_score": profile.authenticity_score,
         "naturalness_score": profile.naturalness_score,
         "catfish_risk_score": profile.catfish_risk_score,
         "bot_risk_score": profile.bot_risk_score},
        trust.get("vetting"),
    )
    trust["overall_trust_score"] = summary["overall_trust_score"]
    trust["catfish_flag"] = summary["catfish_flag"]
    trust["catfish_flag_label"] = summary["catfish_flag_label"]
    profile.trust_analysis = trust

    ranking = db.query(Ranking).filter(Ranking.profile_id == profile.id).first()
    if ranking:
        ranking.x_social_proof_score = report.get("x_social_proof_score")
        score = report.get("x_social_proof_score")
        if score is not None:
            # Social proof nudges percolation: verified-real rises, suspicious sinks
            ranking.percolation_priority += (score - 50) * 0.3

    enrichment = (
        db.query(SocialEnrichment)
        .filter(
            SocialEnrichment.profile_id == profile.id,
            SocialEnrichment.platform == "x",
        )
        .first()
    )
    summary_text = report.get("one_line_summary") or f"X verification: {report['verdict']}"
    findings = {
        "status": "ok" if report.get("x_api_status") == "ok" else report.get("x_api_status"),
        "verdict": report["verdict"],
        "x_social_proof_score": report.get("x_social_proof_score"),
        "usernames": [handle],
        "citations": report.get("citations", []),
        "provider": "x_api+grok_x_search",
    }
    if enrichment:
        enrichment.username = handle
        enrichment.url = report["profile_url"]
        enrichment.summary = summary_text
        enrichment.findings = findings
    else:
        db.add(
            SocialEnrichment(
                profile_id=profile.id,
                platform="x",
                username=handle,
                url=report["profile_url"],
                summary=summary_text,
                findings=findings,
            )
        )

    db.add(
        ProfileEvidence(
            profile_id=profile.id,
            account_id=account_id,
            kind="x_verify",
            content_text=f"@{handle}",
            extracted_json={
                "verdict": report["verdict"],
                "x_social_proof_score": report.get("x_social_proof_score"),
                "one_line_summary": report.get("one_line_summary"),
                "citation_count": len(report.get("citations", [])),
            },
            tokens_charged=0,
        )
    )
    db.flush()


async def generate_verification_questions(
    db: Session, profile: Profile, handle: str
) -> dict:
    """3 personalized questions only the real X account owner could answer."""
    settings = get_settings()
    normalized = x_api_service.normalize_handle(handle)
    if not normalized:
        return {"status": "error", "message": "Invalid X handle."}

    x_data = await x_api_service.fetch_x_profile(db, normalized)
    timeline = x_data.get("timeline") or []

    if x_data.get("status") == "ok" and timeline:
        # Ground questions in official-API timeline data
        prompt = VERIFICATION_QUESTIONS_PROMPT.format(
            handle=normalized,
            x_facts=json.dumps(_x_facts_for_prompt(x_data), indent=2),
            timeline_sample=_timeline_sample(timeline, limit=25),
        )
        parsed, _usage = await llm_service.generate_json(
            prompt, model=settings.xai_text_fast, timeout=180.0
        )
    else:
        # No API key or empty timeline — let Grok's x_search find material itself
        prompt = VERIFICATION_QUESTIONS_PROMPT.format(
            handle=normalized,
            x_facts=json.dumps(_x_facts_for_prompt(x_data), indent=2),
            timeline_sample=(
                "(use X search to review @" + normalized + "'s recent public posts)"
            ),
        )
        parsed, _agentic = await llm_service.generate_agentic_json(
            prompt,
            model=settings.xai_text_reason,
            tools=[{"type": "x_search"}],
            max_turns=4,
            timeout=300.0,
        )

    questions = parsed.get("questions") or []
    if profile.x_verification:
        report = dict(profile.x_verification)
        report["verification_questions"] = questions
        profile.x_verification = report
        db.flush()
    return {"status": "ok", "handle": normalized, "questions": questions}
