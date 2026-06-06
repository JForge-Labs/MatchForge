"""User onboarding endpoints."""
import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.auth import (
    get_account_id,
    is_authenticated,
    redirect_if_unauthenticated,
    require_auth,
)
from app.core.db import get_db
from app.schemas.onboarding import OnboardingProfileOut, OnboardingStatus
from app.services import onboarding_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])
templates = Jinja2Templates(directory="templates")


@router.get("/status", response_model=OnboardingStatus)
def onboarding_status(request: Request, db: Session = Depends(get_db)):
    require_auth(request)
    account_id = get_account_id(request)
    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    pref = onboarding_service.get_user_preference(db, account_id=account_id)
    return OnboardingStatus(
        onboarding_complete=user.onboarding_complete,
        gender=user.gender,
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
    examples: list[UploadFile] | None = File(None),
    db: Session = Depends(get_db),
):
    """Save profile settings and generate personalized match ranking profile."""
    require_auth(request)
    account_id = get_account_id(request)
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

    user = await onboarding_service.complete_onboarding(
        db,
        gender=gender,
        intentions=intent_list,
        preferred_genders=seeking_list,
        example_images=example_bytes or None,
        other_note=other_intention_note,
        account_id=account_id,
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


@router.get("", response_class=HTMLResponse)
def onboarding_ui(request: Request, db: Session = Depends(get_db)):
    if redirect := redirect_if_unauthenticated(request):
        return redirect

    account_id = get_account_id(request)
    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    return templates.TemplateResponse(
        request,
        "onboarding.html",
        {"user": user, "authed": is_authenticated(request), "active": "settings"},
    )