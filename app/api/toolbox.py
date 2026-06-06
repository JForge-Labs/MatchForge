"""Screenshot upload and toolbox endpoints."""
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.auth import get_account_id, require_auth
from app.core.db import get_db
from app.models.profile import Profile, Ranking
from app.schemas.profile import TrustScoresOut, UploadResult
from app.services import (
    credit_service,
    onboarding_service,
    ranking_service,
    referral_service,
    trust_service,
    vetting_service,
    vision_service,
)
from app.services.model_router import route

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/toolbox", tags=["toolbox"])


@router.post("/upload-screenshots", response_model=UploadResult)
async def upload_screenshots(
    request: Request,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Accept screenshots; extract, trust-analyze, rank, persist."""
    require_auth(request)
    account_id = get_account_id(request)
    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    if not user.onboarding_complete:
        raise HTTPException(
            403,
            "Complete your profile settings at /onboarding before uploading screenshots.",
        )

    preference = onboarding_service.get_user_preference(db, account_id=account_id)
    if not preference:
        raise HTTPException(500, "No preference vector — complete onboarding")

    if not files:
        return UploadResult(
            profiles_created=0, profiles=[], message="No files uploaded."
        )

    upload_cost = route("profile_screenshot").token_cost
    valid_files = [f for f in files if f]
    needed = upload_cost * len(valid_files)
    credit_service.ensure_can_afford(
        db, account_id, needed, activity="profile_screenshot"
    )

    user_context = {
        "gender": user.gender,
        "intentions": user.intentions,
        "ui_context": user.ui_context,
    }
    created_profiles: list[Profile] = []
    trust_breakdown: list[TrustScoresOut] = []

    for idx, upload in enumerate(files):
        image_bytes = await upload.read()
        if not image_bytes:
            continue

        analysis = await vision_service.analyze_screenshot(
            image_bytes, user_context=user_context
        )
        if analysis.get("parse_error"):
            raise HTTPException(
                503,
                detail={
                    "error": "vision_failed",
                    "message": "Vision analysis failed — no tokens charged.",
                    "detail": analysis.get("parse_error"),
                },
            )

        credit_service.charge_tokens(
            db, account_id, "profile_screenshot", metadata={"file_index": idx}
        )

        trust = await trust_service.analyze_profile_trust(
            image_bytes_list=[image_bytes],
            bio=analysis.get("bio"),
            profile_metadata=analysis,
        )
        vetting = await vetting_service.vet_profile(
            name=analysis.get("name") or analysis.get("username"),
            bio=analysis.get("bio"),
            location=analysis.get("location") or analysis.get("hometown"),
            extracted_data=analysis,
            trust_analysis=trust,
            run_web_search=True,
        )
        trust = vetting_service.merge_vetting_into_trust(trust, vetting)

        profile = Profile(
            account_id=account_id,
            name=analysis.get("name"),
            username=analysis.get("username"),
            bio=analysis.get("bio"),
            age=analysis.get("age"),
            location=analysis.get("location"),
            platform=analysis.get("platform", "other"),
            extracted_data=analysis,
            vision_analysis=analysis,
            authenticity_score=trust["authenticity_score"],
            naturalness_score=trust["naturalness_score"],
            catfish_risk_score=trust["catfish_risk_score"],
            bot_risk_score=trust["bot_risk_score"],
            trust_analysis=trust,
            status="extracted",
        )
        db.add(profile)
        db.flush()

        photo_path = vision_service.save_screenshot(image_bytes, profile.id, idx)
        profile.photos = [{"path": photo_path, "index": idx}]

        base_scores = await ranking_service.rank_profile(
            profile,
            preference,
            user_gender=user.gender,
            user_intentions=user.intentions,
            ui_context=user.ui_context,
            trust_data=trust,
        )
        scores = trust_service.compute_trust_adjusted_scores(base_scores, trust)
        ranking_service.apply_ranking_to_profile(profile, scores)

        ranking = Ranking(
            profile_id=profile.id,
            preference_vector_id=preference.id,
            overall_score=scores.get("overall_score", 0),
            compatibility_score=scores.get("compatibility_score", 0),
            attractiveness_score=scores.get("attractiveness_score", 0),
            red_flag_score=scores.get("red_flag_score", 0),
            authenticity_score=trust["authenticity_score"],
            naturalness_score=trust["naturalness_score"],
            catfish_risk_score=trust["catfish_risk_score"],
            bot_risk_score=trust["bot_risk_score"],
            trust_explanation=trust.get("trust_explanation"),
            explanation=scores.get("explanation"),
            percolation_priority=scores.get("percolation_priority", 0),
        )
        db.add(ranking)
        created_profiles.append(profile)
        trust_breakdown.append(
            TrustScoresOut(
                authenticity_score=trust["authenticity_score"],
                naturalness_score=trust["naturalness_score"],
                catfish_risk_score=trust["catfish_risk_score"],
                bot_risk_score=trust["bot_risk_score"],
                overall_trust_score=trust.get("overall_trust_score"),
                catfish_flag=trust.get("catfish_flag"),
                catfish_flag_label=trust.get("catfish_flag_label"),
                trust_explanation=trust.get("trust_explanation"),
                trust_badge=trust.get("trust_badge"),
                catfish_badge=trust.get("catfish_badge"),
                bot_badge=trust.get("bot_badge"),
                risk_factors=trust.get("risk_factors", []),
            )
        )

    if created_profiles:
        referral_service.mark_first_upload(db, account_id)

    db.commit()
    for p in created_profiles:
        db.refresh(p)

    balance = credit_service.get_balance(db, account_id)
    return UploadResult(
        profiles_created=len(created_profiles),
        profiles=created_profiles,
        trust_breakdown=trust_breakdown,
        message=(
            f"Processed {len(created_profiles)} screenshot(s). "
            f"Token balance: {balance}."
        ),
    )