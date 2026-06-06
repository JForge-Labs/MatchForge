"""Profile enrichment and feedback endpoints."""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.db import get_db
from app.models.profile import Profile, Ranking, SocialEnrichment
from app.schemas.profile import EnrichRequest, EnrichResult, FeedbackRequest
from app.services import ranking_service, social_enrich_service, trust_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/profiles", tags=["profiles"])


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


@router.post("/enrich", response_model=list[EnrichResult])
async def enrich_profiles(
    body: EnrichRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Queue public social enrichment for one or more profiles."""
    if not body.profile_ids:
        profiles = db.query(Profile).limit(10).all()
    else:
        profiles = db.query(Profile).filter(Profile.id.in_(body.profile_ids)).all()

    if not profiles:
        raise HTTPException(404, "No profiles found")

    results = []
    for profile in profiles:
        profile.enrichment_status = "queued"
        background_tasks.add_task(_run_enrichment, profile.id, body.platforms)
        results.append(
            EnrichResult(profile_id=profile.id, enrichments=[], status="queued")
        )
    db.commit()
    return results


@router.get("/{profile_id}")
def get_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = (
        db.query(Profile)
        .options(joinedload(Profile.social_enrichments))
        .filter(Profile.id == profile_id)
        .first()
    )
    if not profile:
        raise HTTPException(404, "Profile not found")
    return profile


@router.post("/feedback")
def submit_feedback(body: FeedbackRequest, db: Session = Depends(get_db)):
    """Record user feedback to refine future rankings."""
    ranking = db.query(Ranking).filter(Ranking.id == body.ranking_id).first()
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