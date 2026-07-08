"""Profile enrichment, evidence, and feedback endpoints."""
import logging
import shutil
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from sqlalchemy.orm import Session, joinedload

from app.core.auth import get_account_id, require_auth
from app.core.db import get_db
from app.models.profile import Profile, ProfileEvidence, Ranking, SocialEnrichment
from app.schemas.profile import EnrichRequest, EnrichResult, FeedbackRequest, ShareOut
from app.services import (
    agent_service,
    credit_service,
    evidence_service,
    profile_extract_service,
    onboarding_service,
    ranking_service,
    share_service,
    social_enrich_service,
    trust_service,
    vetting_service,
)
from app.services.model_router import route
from app.utils.upload_validation import read_validated_image

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/profiles", tags=["profiles"])


def _owned_profile(db: Session, profile_id: int, account_id: int) -> Profile:
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(404, "Profile not found")
    if profile.account_id and profile.account_id != account_id:
        raise HTTPException(403, "Not your profile")
    return profile


async def _run_enrichment(profile_id: int, platforms: list[str]) -> None:
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        profile = db.query(Profile).filter(Profile.id == profile_id).first()
        if not profile:
            return
        profile.enrichment_status = "running"
        db.commit()

        enrichments = await social_enrich_service.enrich_profile(profile, platforms)
        for e in enrichments:
            db.add(e)
        db.flush()

        vetting = await vetting_service.vet_profile(
            name=profile.name,
            bio=profile.bio,
            location=profile.location,
            extracted_data=profile.extracted_data,
            trust_analysis=profile.trust_analysis,
            social_enrichments=enrichments,
            run_web_search=True,
        )

        if profile.trust_analysis:
            photo_analyses = profile.trust_analysis.get("photo_analyses", [])
            catfish = await trust_service.assess_catfish_risk(
                photo_analyses, profile.bio, enrichments
            )
            profile.trust_analysis["catfish_analysis"] = catfish
            profile.trust_analysis["social_mismatch"] = catfish.get(
                "social_mismatch", False
            )
            profile.catfish_risk_score = catfish.get("catfish_risk_score")
            profile.authenticity_score = catfish.get("authenticity_score")
            trust_note = catfish.get("trust_explanation", "")
            profile.trust_analysis["trust_explanation"] = trust_note
            profile.trust_analysis = trust_service.apply_social_trust_adjustment(
                profile.trust_analysis, enrichments, vetting
            )
            trust_note = profile.trust_analysis.get("trust_explanation", trust_note)

            ranking = (
                db.query(Ranking).filter(Ranking.profile_id == profile.id).first()
            )
            if ranking:
                trust = {
                    **profile.trust_analysis,
                    "catfish_risk_score": profile.catfish_risk_score,
                    "authenticity_score": profile.authenticity_score,
                    "naturalness_score": profile.naturalness_score,
                    "bot_risk_score": profile.bot_risk_score,
                    "trust_explanation": trust_note,
                }
                adjusted = trust_service.compute_trust_adjusted_scores(
                    {
                        "overall_score": ranking.overall_score,
                        "compatibility_score": ranking.compatibility_score,
                        "attractiveness_score": ranking.attractiveness_score,
                        "red_flag_score": ranking.red_flag_score,
                        "explanation": ranking.explanation,
                    },
                    trust,
                )
                ranking.overall_score = adjusted["overall_score"]
                ranking.percolation_priority = adjusted["percolation_priority"]
                ranking.catfish_risk_score = profile.catfish_risk_score
                ranking.authenticity_score = profile.authenticity_score
                ranking.trust_explanation = trust_note
                ranking.explanation = adjusted.get("explanation")

        profile.enrichment_status = "done"
        db.commit()
    except Exception as exc:
        logger.exception("Enrichment failed for profile %s: %s", profile_id, exc)
        profile = db.query(Profile).filter(Profile.id == profile_id).first()
        if profile:
            profile.enrichment_status = "error"
            db.commit()
    finally:
        db.close()


@router.post("/vet-top", response_model=list[EnrichResult])
async def vet_top_candidates(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    limit: int = 5,
):
    """Queue deep vetting (social + web) for top shortlist candidates."""
    require_auth(request)
    account_id = get_account_id(request)
    rankings = (
        db.query(Ranking)
        .join(Profile, Ranking.profile_id == Profile.id)
        .filter(Profile.account_id == account_id)
        .order_by(Ranking.percolation_priority.desc())
        .limit(limit)
        .all()
    )
    profile_ids = [r.profile_id for r in rankings]
    body = EnrichRequest(profile_ids=profile_ids)
    return await enrich_profiles(request, body, background_tasks, db)


@router.post("/enrich", response_model=list[EnrichResult])
async def enrich_profiles(
    request: Request,
    body: EnrichRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Queue public social + web enrichment for one or more profiles."""
    require_auth(request)
    account_id = get_account_id(request)
    if not body.profile_ids:
        profiles = (
            db.query(Profile).filter(Profile.account_id == account_id).limit(10).all()
        )
    else:
        profiles = (
            db.query(Profile)
            .filter(
                Profile.id.in_(body.profile_ids),
                Profile.account_id == account_id,
            )
            .all()
        )

    if not profiles:
        raise HTTPException(404, "No profiles found")

    cost = route("deep_vet").token_cost * len(profiles)
    credit_service.ensure_can_afford(db, account_id, cost, activity="deep_vet")

    results = []
    for profile in profiles:
        credit_service.charge_tokens(db, account_id, "deep_vet", metadata={"profile_id": profile.id})
        profile.enrichment_status = "queued"
        background_tasks.add_task(_run_enrichment, profile.id, body.platforms)
        results.append(
            EnrichResult(profile_id=profile.id, enrichments=[], status="queued")
        )
    db.commit()
    return results


@router.post("/{profile_id}/agent")
async def profile_agent(
    request: Request,
    profile_id: int,
    background_tasks: BackgroundTasks,
    prompt: str = Form(""),
    files: Annotated[list[UploadFile], File()] = [],
    urls: Annotated[list[str], Form()] = [],
    db: Session = Depends(get_db),
):
    """Unified agent enrich: free-text prompt + optional images and social links."""
    require_auth(request)
    account_id = get_account_id(request)
    profile = _owned_profile(db, profile_id, account_id)

    images: list[bytes] = []
    for upload in files or []:
        if not upload:
            continue
        data = await read_validated_image(upload)
        if data:
            images.append(data)

    social_urls: list[str] = []
    seen_urls: set[str] = set()
    for raw in (urls or []) + profile_extract_service.extract_urls_from_text(prompt):
        url = (raw or "").strip()
        if url and url not in seen_urls:
            seen_urls.add(url)
            social_urls.append(url)

    if not prompt.strip() and not images and not social_urls:
        raise HTTPException(400, "Enter a prompt, social link, or attach at least one image.")

    est = agent_service.estimate_agent_cost(prompt, len(images), len(social_urls))
    credit_service.ensure_can_afford(db, account_id, est, activity="profile_agent")

    result = await agent_service.run_agent_prompt(
        db, profile, account_id, prompt.strip(), images, social_urls
    )
    for activity in result.get("charge_activities", []):
        credit_service.charge_tokens(
            db, account_id, activity, metadata={"profile_id": profile_id}
        )

    if result.get("request_deep_vet"):
        background_tasks.add_task(
            _run_enrichment,
            profile_id,
            ["facebook", "instagram", "linkedin", "x"],
        )

    db.commit()
    result["balance"] = credit_service.get_balance(db, account_id)
    return result


@router.post("/{profile_id}/evidence/note")
async def add_profile_note(
    request: Request,
    profile_id: int,
    note: str = Form(...),
    db: Session = Depends(get_db),
):
    require_auth(request)
    account_id = get_account_id(request)
    profile = _owned_profile(db, profile_id, account_id)
    credit_service.charge_tokens(db, account_id, "user_note", metadata={"profile_id": profile_id})
    cost = route("user_note").token_cost
    await evidence_service.add_note(
        db, profile, account_id, note.strip(), tokens_charged=cost
    )
    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    pref = onboarding_service.get_user_preference(db, account_id=account_id)
    if pref:
        credit_service.charge_tokens(db, account_id, "rank_refresh", metadata={"profile_id": profile_id})
        await evidence_service.refresh_ranking(
            db,
            profile,
            pref,
            user_gender=user.gender,
            user_intentions=user.intentions,
            ui_context=user.ui_context,
            user_profile=onboarding_service.user_profile_context(user),
        )
    db.commit()
    return {
        "status": "ok",
        "profile_id": profile_id,
        "balance": credit_service.get_balance(db, account_id),
    }


@router.post("/{profile_id}/evidence/screenshot")
async def add_message_screenshot(
    request: Request,
    profile_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    require_auth(request)
    account_id = get_account_id(request)
    profile = _owned_profile(db, profile_id, account_id)
    image_bytes = await read_validated_image(file)
    if not image_bytes:
        raise HTTPException(400, "Empty file")
    credit_service.charge_tokens(
        db, account_id, "message_screenshot", metadata={"profile_id": profile_id}
    )
    cost = route("message_screenshot").token_cost
    await evidence_service.add_message_screenshot(
        db, profile, account_id, image_bytes, tokens_charged=cost
    )
    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    pref = onboarding_service.get_user_preference(db, account_id=account_id)
    if pref:
        credit_service.charge_tokens(db, account_id, "rank_refresh", metadata={"profile_id": profile_id})
        await evidence_service.refresh_ranking(
            db,
            profile,
            pref,
            user_gender=user.gender,
            user_intentions=user.intentions,
            ui_context=user.ui_context,
            user_profile=onboarding_service.user_profile_context(user),
        )
    db.commit()
    return {
        "status": "ok",
        "profile_id": profile_id,
        "balance": credit_service.get_balance(db, account_id),
    }


@router.get("/rankings/{ranking_id}/share", response_model=ShareOut)
def share_ranking_analysis(
    request: Request, ranking_id: int, db: Session = Depends(get_db)
):
    """Build share text + public link; always includes the sharer's referral URL."""
    require_auth(request)
    account_id = get_account_id(request)
    payload = share_service.build_share_payload(db, account_id, ranking_id)
    if not payload:
        raise HTTPException(404, "Ranking not found")
    return payload


@router.delete("/{profile_id}")
def delete_profile(
    request: Request, profile_id: int, db: Session = Depends(get_db)
):
    """Remove a profile workup and all associated rankings, evidence, and uploads."""
    require_auth(request)
    account_id = get_account_id(request)
    profile = _owned_profile(db, profile_id, account_id)

    db.query(Ranking).filter(Ranking.profile_id == profile_id).delete(
        synchronize_session=False
    )
    db.query(SocialEnrichment).filter(
        SocialEnrichment.profile_id == profile_id
    ).delete(synchronize_session=False)
    db.query(ProfileEvidence).filter(
        ProfileEvidence.profile_id == profile_id
    ).delete(synchronize_session=False)
    db.delete(profile)

    upload_dir = Path("data/uploads") / str(profile_id)
    if upload_dir.is_dir():
        shutil.rmtree(upload_dir, ignore_errors=True)

    db.commit()
    return {"status": "deleted", "profile_id": profile_id}


@router.get("/{profile_id}")
def get_profile(
    request: Request, profile_id: int, db: Session = Depends(get_db)
):
    require_auth(request)
    account_id = get_account_id(request)
    profile = (
        db.query(Profile)
        .options(
            joinedload(Profile.social_enrichments),
            joinedload(Profile.evidence),
        )
        .filter(Profile.id == profile_id, Profile.account_id == account_id)
        .first()
    )
    if not profile:
        raise HTTPException(404, "Profile not found")
    return profile


@router.post("/feedback")
def submit_feedback(
    request: Request, body: FeedbackRequest, db: Session = Depends(get_db)
):
    """Record user feedback to refine future rankings."""
    require_auth(request)
    account_id = get_account_id(request)
    ranking = (
        db.query(Ranking)
        .join(Profile, Ranking.profile_id == Profile.id)
        .filter(
            Ranking.id == body.ranking_id,
            Profile.account_id == account_id,
        )
        .first()
    )
    if not ranking:
        raise HTTPException(404, "Ranking not found")

    ranking.feedback = body.feedback
    if body.feedback == "superlike":
        ranking.user_override_rank = 1
        ranking.percolation_priority = 999.0
    elif body.feedback == "like":
        ranking.percolation_priority = ranking.overall_score + 20
    elif body.feedback == "dislike":
        ranking.percolation_priority = ranking.overall_score - 50
    else:
        ranking.percolation_priority = ranking.overall_score - 10

    db.commit()
    return {"status": "ok", "ranking_id": ranking.id, "feedback": body.feedback}