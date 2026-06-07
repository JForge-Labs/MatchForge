"""User onboarding endpoints."""
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.auth import (
    get_account_id,
    is_authenticated,
    redirect_if_unauthenticated,
    require_auth,
)
from app.core.db import get_db
from app.schemas.onboarding import OnboardingProfileOut, OnboardingStatus
from app.services import capacity_service, legal_service, onboarding_service
from app.utils.legal import policies_accepted
from app.utils.templates import render

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/status", response_model=OnboardingStatus)
def onboarding_status(request: Request, db: Session = Depends(get_db)):
    require_auth(request)
    account_id = get_account_id(request)
    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    pref = onboarding_service.get_user_preference(db, account_id=account_id)
    return OnboardingStatus(
        policies_accepted=policies_accepted(user),
        policies_version=user.policies_version,
        onboarding_complete=user.onboarding_complete,
        gender=user.gender,
        display_name=user.display_name,
        age=user.age,
        location=user.location,
        bio=user.bio,
        has_profile_photo=bool(user.avatar_path),
        preferred_genders=user.preferred_genders or [],
        intentions=user.intentions or [],
        has_preference_vector=pref is not None,
        preference_vector=pref,
    )


@router.post("/profile", response_model=OnboardingProfileOut)
async def save_profile(
    request: Request,
    gender: str = Form(...),
    preferred_genders: str = Form(...),
    intentions: str = Form(...),
    other_intention_note: str | None = Form(None),
    display_name: str | None = Form(None),
    age: str | None = Form(None),
    location: str | None = Form(None),
    bio: str | None = Form(None),
    avatar: UploadFile | None = File(None),
    examples: list[UploadFile] | None = File(None),
    db: Session = Depends(get_db),
):
    """Save profile settings and generate personalized match ranking profile."""
    require_auth(request)
    account_id = get_account_id(request)
    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    if not policies_accepted(user):
        raise HTTPException(403, legal_service.require_policies_message())
    if gender not in ("male", "female"):
        raise HTTPException(400, "Select male or female for your gender.")
    seeking_list = (
        json.loads(preferred_genders)
        if preferred_genders.startswith("[")
        else [g.strip() for g in preferred_genders.split(",") if g.strip()]
    )
    seeking_list = [g for g in seeking_list if g in ("male", "female")]
    if not seeking_list:
        raise HTTPException(400, "Select at least one gender to match with.")
    intent_list = json.loads(intentions) if intentions.startswith("[") else [
        i.strip() for i in intentions.split(",") if i.strip()
    ]
    example_bytes: list[bytes] = []
    for upload in examples or []:
        data = await upload.read()
        if data:
            example_bytes.append(data)

    parsed_age: int | None = None
    if age and age.strip().isdigit():
        parsed_age = int(age.strip())

    avatar_bytes: bytes | None = None
    if avatar:
        avatar_bytes = await avatar.read()
        if not avatar_bytes:
            avatar_bytes = None

    async with capacity_service.heavy_work_slot():
        user = await onboarding_service.complete_onboarding(
            db,
            gender=gender,
            intentions=intent_list,
            preferred_genders=seeking_list,
            example_images=example_bytes or None,
            other_note=other_intention_note,
            account_id=account_id,
            display_name=display_name,
            age=parsed_age,
            location=location,
            bio=bio,
            avatar_bytes=avatar_bytes,
        )
    pref = onboarding_service.get_user_preference(db, account_id=account_id)
    return OnboardingProfileOut(
        onboarding_complete=True,
        gender=user.gender,
        intentions=user.intentions,
        preference_vector=pref,
        ui_context=user.ui_context,
        example_count=len(user.example_analyses or []),
        message="Profile saved — your match ranking profile is ready.",
    )


@router.get("/media/{kind}")
def user_media(kind: str, request: Request, db: Session = Depends(get_db)):
    """Serve saved profile photo for settings preview."""
    require_auth(request)
    if kind != "avatar":
        raise HTTPException(404, "Not found")
    account_id = get_account_id(request)
    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    path_str = user.avatar_path
    if not path_str:
        raise HTTPException(404, "No image uploaded")
    path = Path(path_str)
    if not path.is_file():
        raise HTTPException(404, "File missing")
    return FileResponse(path, media_type="image/jpeg")


@router.get("", response_class=HTMLResponse)
def onboarding_ui(request: Request, db: Session = Depends(get_db)):
    if redirect := redirect_if_unauthenticated(request):
        return redirect

    account_id = get_account_id(request)
    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    if not policies_accepted(user):
        return RedirectResponse(url="/legal/accept", status_code=302)
    return render(
        request,
        "onboarding.html",
        {"user": user, "authed": is_authenticated(request), "active": "settings"},
        db=db,
    )