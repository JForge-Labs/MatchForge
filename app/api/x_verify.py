"""X verification endpoints — handle input, agentic verification, questions.

Consent model: verification only runs when the user explicitly submits a
handle and checks the public-data acknowledgement. Only public X data is
fetched; everything is deleted with the profile/account.
"""
import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.auth import get_account_id, require_auth
from app.core.db import get_db
from app.models.profile import Profile
from urllib.parse import quote_plus

from app.services import (
    credit_service,
    onboarding_service,
    ranking_service,
    share_service,
    x_api_service,
    x_verify_service,
)
from app.services.model_router import route

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/profiles", tags=["x-verify"])


def _owned_profile(db: Session, profile_id: int, account_id: int) -> Profile:
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(404, "Profile not found")
    # Strict ownership — a NULL account_id must not grant everyone access.
    if profile.account_id != account_id:
        raise HTTPException(403, "Not your profile")
    return profile


async def _rank_new_profile(db: Session, profile: Profile, account_id: int) -> None:
    """Create a Ranking for a handle-first profile (mirrors the upload flow)."""
    from app.models.profile import Ranking
    from app.services import trust_service

    pref = onboarding_service.get_user_preference(db, account_id=account_id)
    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    if not pref:
        return
    trust = profile.trust_analysis or {}
    base_scores = await ranking_service.rank_profile(
        profile,
        pref,
        user_gender=user.gender,
        user_intentions=user.intentions,
        ui_context=user.ui_context,
        user_profile=onboarding_service.user_profile_context(user),
    )
    scores = trust_service.compute_trust_adjusted_scores(base_scores, trust)
    ranking_service.apply_ranking_to_profile(profile, scores)
    db.add(
        Ranking(
            profile_id=profile.id,
            preference_vector_id=pref.id,
            overall_score=scores.get("overall_score", 0),
            compatibility_score=scores.get("compatibility_score", 0),
            attractiveness_score=scores.get("attractiveness_score", 0),
            red_flag_score=scores.get("red_flag_score", 0),
            authenticity_score=trust.get("authenticity_score"),
            catfish_risk_score=trust.get("catfish_risk_score"),
            bot_risk_score=trust.get("bot_risk_score"),
            x_social_proof_score=profile.x_social_proof_score,
            trust_explanation=trust.get("trust_explanation"),
            explanation=scores.get("explanation"),
            percolation_priority=scores.get("percolation_priority", 0),
        )
    )
    db.flush()


def _require_valid_handle(x_username: str) -> str:
    handle = x_api_service.normalize_handle(x_username)
    if not handle:
        raise HTTPException(
            400, "Enter a valid X handle (@name) or x.com profile link."
        )
    return handle


@router.post("/{profile_id}/x-verify")
async def verify_profile_on_x(
    request: Request,
    profile_id: int,
    x_username: str = Form(...),
    consent: bool = Form(False),
    db: Session = Depends(get_db),
):
    """Run the agentic X verification on an existing profile tile."""
    require_auth(request)
    account_id = get_account_id(request)
    if not consent:
        raise HTTPException(
            400,
            "Please confirm you understand this checks public X data only.",
        )
    profile = _owned_profile(db, profile_id, account_id)
    handle = _require_valid_handle(x_username)

    cost = route("x_verify").token_cost
    credit_service.ensure_can_afford(db, account_id, cost, activity="x_verify")
    credit_service.charge_tokens(
        db, account_id, "x_verify", metadata={"profile_id": profile_id, "handle": handle}
    )

    result = await x_verify_service.run_x_verification(db, profile, account_id, handle)
    if result.get("status") != "ok":
        db.commit()  # keep the charge ledger consistent; verification recorded the failure
        raise HTTPException(422, result.get("message", "Verification failed"))

    db.commit()
    return {
        **result,
        "profile_id": profile_id,
        "tokens_charged": cost,
        "balance": credit_service.get_balance(db, account_id),
    }


@router.post("/x-lookup")
async def lookup_by_x_handle(
    request: Request,
    x_username: str = Form(...),
    consent: bool = Form(False),
    db: Session = Depends(get_db),
):
    """Create a profile from an X handle alone (no screenshot) and verify it."""
    require_auth(request)
    account_id = get_account_id(request)
    if not consent:
        raise HTTPException(
            400,
            "Please confirm you understand this checks public X data only.",
        )
    handle = _require_valid_handle(x_username)

    cost = route("x_verify").token_cost
    credit_service.ensure_can_afford(db, account_id, cost, activity="x_verify")

    existing = (
        db.query(Profile)
        .filter(
            Profile.account_id == account_id,
            Profile.platform == "x",
            Profile.username.ilike(handle),
        )
        .first()
    )
    profile = existing or Profile(
        account_id=account_id,
        username=handle,
        platform="x",
        extracted_data={"profile_url": f"https://x.com/{handle}", "x_handle": handle},
        enrichment_status="pending",
    )
    if not existing:
        db.add(profile)
        db.flush()

    credit_service.charge_tokens(
        db, account_id, "x_verify", metadata={"profile_id": profile.id, "handle": handle}
    )

    result = await x_verify_service.run_x_verification(db, profile, account_id, handle)
    if result.get("status") != "ok":
        db.commit()
        raise HTTPException(422, result.get("message", "Verification failed"))

    # Backfill display fields from the X account for handle-first profiles
    report = result["report"]
    facts = report.get("account_facts") or {}
    if facts.get("available"):
        if not profile.name:
            profile.name = facts.get("display_name")
        if not profile.bio:
            profile.bio = facts.get("bio")
        if not profile.location:
            profile.location = facts.get("location")

    # Rank handle-first profiles so they appear on the shortlist
    if not existing:
        try:
            await _rank_new_profile(db, profile, account_id)
        except Exception as exc:
            logger.warning("Ranking after x-lookup failed: %s", exc)

    profile.enrichment_status = "done"
    db.commit()
    return {
        **result,
        "profile_id": profile.id,
        "created": not bool(existing),
        "tokens_charged": cost,
        "balance": credit_service.get_balance(db, account_id),
    }


@router.post("/{profile_id}/x-verify/share")
def share_x_verification(
    request: Request,
    profile_id: int,
    db: Session = Depends(get_db),
):
    """Opt-in: publish this verification as a public badge page + OG card."""
    require_auth(request)
    account_id = get_account_id(request)
    profile = _owned_profile(db, profile_id, account_id)
    report = profile.x_verification or {}
    if not report.get("verdict"):
        raise HTTPException(400, "Run an X verification first.")

    # Explicit opt-in flag — the public page refuses to render without it
    report = dict(report)
    report["share_enabled"] = True
    profile.x_verification = report
    db.commit()

    token = share_service.create_verify_token(account_id, profile_id)
    share_url = share_service.build_verify_share_url(token)
    score = report.get("x_social_proof_score")
    text = (
        f"@{report['handle']} passed an AI dating-safety check — "
        f"X Social Proof {score:.0f}/100. " if score is not None
        else f"@{report['handle']} — AI dating-safety check. "
    ) + "Verified with MatchForge (X API + Grok)."
    intent_url = (
        "https://twitter.com/intent/tweet?text="
        + quote_plus(text)
        + "&url="
        + quote_plus(share_url)
    )
    return {
        "status": "ok",
        "share_url": share_url,
        "badge_url": f"{share_url}/badge.png",
        "intent_url": intent_url,
        "text": text,
    }


@router.post("/{profile_id}/x-verify/questions")
async def verification_questions(
    request: Request,
    profile_id: int,
    x_username: str = Form(""),
    db: Session = Depends(get_db),
):
    """Generate 3 questions only the real X account owner could answer."""
    require_auth(request)
    account_id = get_account_id(request)
    profile = _owned_profile(db, profile_id, account_id)

    handle = x_username.strip() or (profile.x_verification or {}).get("handle") or ""
    handle = _require_valid_handle(handle)

    cost = route("verification_questions").token_cost
    credit_service.ensure_can_afford(
        db, account_id, cost, activity="verification_questions"
    )
    credit_service.charge_tokens(
        db,
        account_id,
        "verification_questions",
        metadata={"profile_id": profile_id, "handle": handle},
    )

    result = await x_verify_service.generate_verification_questions(
        db, profile, handle
    )
    if result.get("status") != "ok":
        db.commit()
        raise HTTPException(422, result.get("message", "Question generation failed"))
    db.commit()
    return {
        **result,
        "profile_id": profile_id,
        "tokens_charged": cost,
        "balance": credit_service.get_balance(db, account_id),
    }
