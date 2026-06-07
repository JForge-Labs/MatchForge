"""Public legal documents and policy acceptance."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.auth import (
    get_account_id,
    is_authenticated,
    redirect_if_unauthenticated,
    require_auth,
)
from app.core.db import get_db
from app.schemas.legal import PolicyAcceptanceOut
from app.services import legal_service, onboarding_service
from app.utils.legal import POLICIES_VERSION, policies_accepted, post_auth_path
from app.utils.templates import render

router = APIRouter(tags=["legal"])


@router.get("/legal/terms", response_class=HTMLResponse)
def terms_page(request: Request):
    return render(
        request,
        "legal/terms.html",
        {"authed": is_authenticated(request), "active": None, "policies_version": POLICIES_VERSION},
    )


@router.get("/legal/privacy", response_class=HTMLResponse)
def privacy_page(request: Request):
    return render(
        request,
        "legal/privacy.html",
        {"authed": is_authenticated(request), "active": None, "policies_version": POLICIES_VERSION},
    )


@router.get("/legal/accept", response_class=HTMLResponse)
def accept_policies_page(request: Request, db: Session = Depends(get_db)):
    if redirect := redirect_if_unauthenticated(request):
        return redirect

    account_id = get_account_id(request)
    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    if policies_accepted(user):
        return RedirectResponse(url=post_auth_path(user), status_code=302)

    return render(
        request,
        "legal/accept.html",
        {
            "user": user,
            "authed": True,
            "active": None,
            "policies_version": POLICIES_VERSION,
        },
    )


@router.post("/onboarding/accept-policies", response_model=PolicyAcceptanceOut)
def accept_policies_api(request: Request, db: Session = Depends(get_db)):
    require_auth(request)
    account_id = get_account_id(request)
    user = legal_service.accept_policies(db, account_id=account_id)
    return PolicyAcceptanceOut(
        accepted=True,
        policies_version=user.policies_version,
        policies_accepted_at=user.policies_accepted_at,
        next_url=post_auth_path(user),
        message="Policies accepted. You can continue setting up your profile.",
    )


@router.post("/legal/accept")
def accept_policies_form(
    request: Request,
    agree: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if redirect := redirect_if_unauthenticated(request):
        return redirect
    if not agree:
        account_id = get_account_id(request)
        user = onboarding_service.get_or_create_user(db, account_id=account_id)
        return render(
            request,
            "legal/accept.html",
            {
                "user": user,
                "authed": True,
                "active": None,
                "policies_version": POLICIES_VERSION,
                "error": "You must agree to the Terms and Privacy Policy to continue.",
            },
            status_code=400,
        )

    account_id = get_account_id(request)
    user = legal_service.accept_policies(db, account_id=account_id)
    return RedirectResponse(url=post_auth_path(user), status_code=302)