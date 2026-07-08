"""Screenshot upload endpoints — async job pipeline with real progress."""
import asyncio
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.auth import get_account_id, require_auth
from app.core.db import SessionLocal, get_db
from app.models.profile import Profile, Ranking
from app.services import (
    capacity_service,
    credit_service,
    legal_service,
    onboarding_service,
    profile_merge_service,
    ranking_service,
    referral_service,
    trust_service,
    upload_jobs,
    vetting_service,
    vision_service,
)
from app.services.model_router import route
from app.utils.upload_validation import MAX_FILES_PER_BATCH, read_validated_image

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/toolbox", tags=["toolbox"])


@router.post("/upload-screenshots", status_code=202)
async def upload_screenshots(
    request: Request,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Validate + accept screenshots, then analyze in the background.

    Returns 202 with a job id immediately; the dashboard polls
    /toolbox/upload-jobs/{job_id} for real per-file progress.
    """
    require_auth(request)
    account_id = get_account_id(request)
    ratelimit.enforce(
        request,
        scope="upload",
        limit=30,
        window_seconds=3600,
        identity=str(account_id),
    )
    from app.utils.legal import policies_accepted

    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    if not policies_accepted(user):
        raise HTTPException(403, legal_service.require_policies_message())
    if not user.onboarding_complete:
        raise HTTPException(
            403,
            "Complete your profile settings at /onboarding before uploading screenshots.",
        )
    if not onboarding_service.get_user_preference(db, account_id=account_id):
        raise HTTPException(500, "No preference vector — complete onboarding")

    valid_files = [f for f in files if f]
    if not valid_files:
        raise HTTPException(
            422, detail={"error": "no_files", "message": "No files uploaded."}
        )
    if len(valid_files) > MAX_FILES_PER_BATCH:
        raise HTTPException(
            422,
            detail={
                "error": "too_many_files",
                "message": (
                    f"Upload up to {MAX_FILES_PER_BATCH} screenshots at a time. "
                    "No tokens were charged."
                ),
            },
        )

    # Read + validate everything before accepting: invalid files become
    # pre-failed job entries so the progress UI reports them honestly.
    payloads: list[tuple[str, bytes | None, str | None]] = []
    for idx, upload in enumerate(valid_files):
        filename = upload.filename or f"screenshot {idx + 1}"
        try:
            data = await read_validated_image(upload)
        except HTTPException as exc:
            reason = (
                exc.detail.get("message")
                if isinstance(exc.detail, dict)
                else str(exc.detail)
            )
            payloads.append((filename, None, reason))
            continue
        if data:
            payloads.append((filename, data, None))

    good = [p for p in payloads if p[1] is not None]
    if not good:
        raise HTTPException(
            422,
            detail={
                "error": "all_files_failed",
                "message": " ".join(f"{n}: {e}" for n, _, e in payloads)
                or "No readable files uploaded.",
            },
        )

    upload_cost = route("profile_screenshot").token_cost
    credit_service.ensure_can_afford(
        db, account_id, upload_cost * len(good), activity="profile_screenshot"
    )
    capacity_service.raise_if_overloaded()

    job = upload_jobs.create_job(account_id, [p[0] for p in payloads])
    for i, (_, data, err) in enumerate(payloads):
        if err or data is None:
            upload_jobs.set_file_stage(job, i, "failed", error=err or "Empty file")

    asyncio.create_task(_process_upload_job(job, payloads))
    return JSONResponse(
        status_code=202,
        content={
            "job_id": job["id"],
            "files": [p[0] for p in payloads],
            "status_url": f"/toolbox/upload-jobs/{job['id']}",
        },
    )


@router.get("/upload-jobs/{job_id}")
def upload_job_status(request: Request, job_id: str):
    """Poll target for the upload progress UI."""
    require_auth(request)
    job = upload_jobs.get_job(job_id, get_account_id(request))
    if not job:
        raise HTTPException(404, "Job not found")
    return upload_jobs.public_view(job)


async def _acquire_heavy_slot(job: dict):
    """Wait for a capacity slot instead of failing the accepted job outright."""
    for attempt in range(20):  # ~5 minutes of patience
        try:
            ctx = capacity_service.heavy_work_slot()
            await ctx.__aenter__()
            return ctx
        except HTTPException as exc:
            capacity = (
                isinstance(exc.detail, dict) and exc.detail.get("error") == "capacity"
            )
            if not capacity or attempt == 19:
                raise
            job["message"] = (
                "Waiting for an analysis slot — high demand right now…"
            )
            await asyncio.sleep(15)
    raise RuntimeError("unreachable")


async def _process_upload_job(
    job: dict, payloads: list[tuple[str, bytes | None, str | None]]
) -> None:
    account_id = job["account_id"]
    db = SessionLocal()
    job["status"] = "running"
    created_count = 0
    merged_count = 0
    try:
        user = onboarding_service.get_or_create_user(db, account_id=account_id)
        preference = onboarding_service.get_user_preference(db, account_id=account_id)
        if not preference:
            job["status"] = "error"
            job["error"] = "No preference vector — complete onboarding first."
            return
        user_context = {
            "gender": user.gender,
            "intentions": user.intentions,
            "ui_context": user.ui_context,
        }
        upload_cost = route("profile_screenshot").token_cost

        try:
            slot = await _acquire_heavy_slot(job)
        except HTTPException as exc:
            message = (
                exc.detail.get("message")
                if isinstance(exc.detail, dict)
                else str(exc.detail)
            )
            job["status"] = "error"
            job["error"] = message
            for i, entry in enumerate(job["files"]):
                if entry["stage"] == "queued":
                    upload_jobs.set_file_stage(
                        job, i, "failed", error="Skipped — at capacity."
                    )
            return

        try:
            for idx, (filename, image_bytes, pre_error) in enumerate(payloads):
                if pre_error or image_bytes is None:
                    continue
                upload_jobs.set_file_stage(job, idx, "analyzing")
                try:
                    # Grok call 1 of 2: extraction + photo forensics
                    analysis, photo_trust = (
                        await vision_service.analyze_screenshot_full(
                            image_bytes, user_context=user_context
                        )
                    )
                    if analysis.get("parse_error"):
                        upload_jobs.set_file_stage(
                            job,
                            idx,
                            "failed",
                            error=(
                                "Vision analysis failed — no tokens charged "
                                "for this file."
                            ),
                        )
                        continue

                    credit_service.charge_tokens(
                        db,
                        account_id,
                        "profile_screenshot",
                        metadata={"file_index": idx},
                    )

                    existing = profile_merge_service.find_existing_profile(
                        db, account_id, analysis
                    )
                    is_merge = existing is not None

                    if is_merge:
                        profile = existing
                        photo_path = vision_service.save_screenshot(
                            image_bytes, profile.id, len(profile.photos or [])
                        )
                        profile_merge_service.merge_analysis_into_profile(
                            profile,
                            analysis,
                            photo_path=photo_path,
                            photo_index=len(profile.photos or []),
                        )
                    else:
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
                            status="extracted",
                        )
                        db.add(profile)
                        db.flush()
                        photo_path = vision_service.save_screenshot(
                            image_bytes, profile.id, idx
                        )
                        profile.photos = [{"path": photo_path, "index": idx}]

                    # Forensics cache: only this screenshot was vision-analyzed
                    photo_trust["photo_path"] = photo_path
                    prior_forensics = [
                        p
                        for p in (profile.trust_analysis or {}).get(
                            "photo_analyses", []
                        )
                        if p.get("photo_path") != photo_path
                    ]
                    photo_analyses = (prior_forensics + [photo_trust])[-10:]

                    upload_jobs.set_file_stage(job, idx, "scoring")

                    # Grok call 2 of 2: bot + catfish + personalized fit
                    assessment = await trust_service.synthesize_profile_assessment(
                        profile=profile,
                        photo_analyses=photo_analyses,
                        bio=profile.bio or analysis.get("bio"),
                        profile_metadata={
                            **(profile.extracted_data or {}),
                            **analysis,
                        },
                        social_enrichments=[],
                        preference=preference,
                        user_gender=user.gender,
                        user_intentions=user.intentions,
                        ui_context=user.ui_context,
                        user_profile=onboarding_service.user_profile_context(user),
                    )
                    trust = trust_service.build_trust_result(
                        photo_analyses, assessment["bot"], assessment["catfish"]
                    )

                    vetting = await vetting_service.vet_profile(
                        name=profile.name or analysis.get("username"),
                        bio=profile.bio or analysis.get("bio"),
                        location=profile.location or analysis.get("hometown"),
                        extracted_data=profile.extracted_data or analysis,
                        trust_analysis=trust,
                        run_web_search=True,
                    )
                    trust = vetting_service.merge_vetting_into_trust(trust, vetting)
                    profile_merge_service.merge_trust_into_profile(profile, trust)

                    spent = dict(profile.extracted_data or {})
                    spent["tokens_spent"] = (
                        int(spent.get("tokens_spent") or 0) + upload_cost
                    )
                    profile.extracted_data = spent

                    base_scores = assessment["ranking"]
                    scores = trust_service.compute_trust_adjusted_scores(
                        base_scores, trust
                    )
                    ranking_service.apply_ranking_to_profile(profile, scores)

                    ranking = (
                        db.query(Ranking)
                        .filter(Ranking.profile_id == profile.id)
                        .first()
                    )
                    if ranking:
                        ranking_service.snapshot_ranking(
                            ranking, "New screenshot analyzed"
                        )
                        ranking.overall_score = scores.get("overall_score", 0)
                        ranking.compatibility_score = scores.get(
                            "compatibility_score", 0
                        )
                        ranking.attractiveness_score = scores.get(
                            "attractiveness_score", 0
                        )
                        ranking.red_flag_score = scores.get("red_flag_score", 0)
                        ranking.authenticity_score = trust["authenticity_score"]
                        ranking.catfish_risk_score = trust["catfish_risk_score"]
                        ranking.bot_risk_score = trust["bot_risk_score"]
                        ranking.trust_explanation = trust.get("trust_explanation")
                        ranking.explanation = scores.get("explanation")
                        ranking.percolation_priority = scores.get(
                            "percolation_priority", 0
                        )
                        ranking_service.apply_feedback_percolation(ranking)
                    else:
                        ranking = Ranking(
                            profile_id=profile.id,
                            preference_vector_id=preference.id,
                            overall_score=scores.get("overall_score", 0),
                            compatibility_score=scores.get("compatibility_score", 0),
                            attractiveness_score=scores.get(
                                "attractiveness_score", 0
                            ),
                            red_flag_score=scores.get("red_flag_score", 0),
                            authenticity_score=trust["authenticity_score"],
                            catfish_risk_score=trust["catfish_risk_score"],
                            bot_risk_score=trust["bot_risk_score"],
                            trust_explanation=trust.get("trust_explanation"),
                            explanation=scores.get("explanation"),
                            percolation_priority=scores.get(
                                "percolation_priority", 0
                            ),
                        )
                        db.add(ranking)

                    # Per-file durability: later failures can't roll back
                    # profiles the user already paid to analyze.
                    db.commit()
                    profile_id = profile.id
                    if is_merge:
                        merged_count += 1
                    else:
                        created_count += 1
                    upload_jobs.set_file_stage(
                        job, idx, "done", profile_id=profile_id, merged=is_merge
                    )
                except HTTPException as exc:
                    db.rollback()
                    detail = exc.detail
                    reason = (
                        detail.get("message")
                        if isinstance(detail, dict)
                        else str(detail)
                    )
                    upload_jobs.set_file_stage(job, idx, "failed", error=reason)
                    if (
                        isinstance(detail, dict)
                        and detail.get("error") == "insufficient_tokens"
                    ):
                        for j in range(idx + 1, len(payloads)):
                            if job["files"][j]["stage"] == "queued":
                                upload_jobs.set_file_stage(
                                    job,
                                    j,
                                    "failed",
                                    error="Skipped — insufficient tokens.",
                                )
                        break
                except Exception:
                    logger.exception("Upload processing failed for %s", filename)
                    db.rollback()
                    upload_jobs.set_file_stage(
                        job,
                        idx,
                        "failed",
                        error=(
                            "Analysis failed — no tokens were charged for "
                            "this file."
                        ),
                    )

            if created_count:
                referral_service.mark_first_upload(db, account_id)
            profile_merge_service.merge_duplicate_profiles(db, account_id)
            db.commit()
        finally:
            await slot.__aexit__(None, None, None)

        balance = credit_service.get_balance(db, account_id)
        processed = created_count + merged_count
        failed = [f for f in job["files"] if f["stage"] == "failed"]
        message = (
            f"Processed {processed} screenshot(s)"
            f" ({created_count} new, {merged_count} merged)."
            f" Token balance: {balance}."
        )
        if failed:
            message += " Skipped: " + " ".join(
                f"{f['name']}: {f['error']}" for f in failed
            )
        job["balance"] = balance
        job["message"] = message
        job["status"] = "done"
    except Exception:
        logger.exception("Upload job %s failed", job["id"])
        job["status"] = "error"
        job["error"] = (
            "Analysis failed unexpectedly — any completed profiles are "
            "already on your dashboard."
        )
    finally:
        db.close()
