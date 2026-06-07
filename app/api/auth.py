"""Signup, email verification, login, and logout."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.auth import (
    get_account_id,
    is_authenticated,
    login_user,
    logout_user,
    verify_password,
)
from app.core.config import get_settings
from app.core.db import get_db
from app.services import account_service, email_service
from app.services import onboarding_service
from app.utils.legal import post_auth_path
from app.utils.social_meta import REFERRAL_OG_DESCRIPTION, REFERRAL_OG_TITLE
from app.utils.templates import render

router = APIRouter(tags=["auth"])


def _auth_context(**extra):
    return {
        "authed": False,
        "smtp_configured": email_service.smtp_configured(),
        **extra,
    }


@router.get("/signup", response_class=HTMLResponse)
def signup_page(
    request: Request,
    db: Session = Depends(get_db),
    error: str | None = None,
    ref: str | None = None,
):
    if is_authenticated(request):
        account_id = get_account_id(request)
        user = onboarding_service.get_or_create_user(db, account_id=account_id)
        return RedirectResponse(url=post_auth_path(user), status_code=302)
    return render(
        request,
        "signup.html",
        _auth_context(
            error=error,
            referral_code=ref or "",
            referral_og_title=REFERRAL_OG_TITLE,
            referral_og_description=REFERRAL_OG_DESCRIPTION,
            **(
                {
                    "og_title": REFERRAL_OG_TITLE,
                    "og_description": REFERRAL_OG_DESCRIPTION,
                    "twitter_title": REFERRAL_OG_TITLE,
                    "twitter_description": REFERRAL_OG_DESCRIPTION,
                    "og_url": f"{get_settings().app_url.rstrip('/')}/signup?ref={ref}",
                }
                if ref
                else {}
            ),
        ),
    )


@router.post("/signup")
def signup_submit(
    request: Request,
    email: str = Form(...),
    referral_code: str = Form(""),
    db: Session = Depends(get_db),
):
    status, dev_token = account_service.request_signup(
        db, email, referral_code=referral_code or None
    )
    if status == "invalid":
        return render(
            request,
            "signup.html",
            _auth_context(error="Enter a valid email address."),
            status_code=400,
        )
    if status == "exists":
        return render(
            request,
            "signup.html",
            _auth_context(
                error="An account with this email already exists. Sign in instead.",
                email=account_service.normalize_email(email),
            ),
            status_code=409,
        )

    dev_link = (
        account_service.build_auth_url(dev_token, "signup_verify") if dev_token else None
    )
    return render(
        request,
        "auth_email_sent.html",
        _auth_context(
            email=account_service.normalize_email(email),
            purpose="signup",
            dev_link=dev_link,
        ),
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    next: str = "/dashboard",
    error: str | None = None,
    mode: str = "email",
):
    if is_authenticated(request):
        return RedirectResponse(url=next, status_code=302)
    return render(
        request,
        "login.html",
        _auth_context(next=next, error=error, mode=mode),
    )


@router.post("/login")
def login_submit(
    request: Request,
    mode: str = Form("email"),
    email: str = Form(""),
    password: str = Form(""),
    next: str = Form("/dashboard"),
    db: Session = Depends(get_db),
):
    if mode == "password":
        if not verify_password(password):
            return render(
                request,
                "login.html",
                _auth_context(
                    next=next,
                    error="Incorrect password. Try again.",
                    mode="password",
                ),
                status_code=401,
            )
        login_user(request)
        account_id = get_account_id(request)
        user = onboarding_service.get_or_create_user(db, account_id=account_id)
        return RedirectResponse(url=post_auth_path(user), status_code=302)

    status, dev_token = account_service.request_login_link(db, email)
    if status == "invalid":
        return render(
            request,
            "login.html",
            _auth_context(
                next=next,
                error="Enter a valid email address.",
                mode="email",
                email=email,
            ),
            status_code=400,
        )
    if status == "not_found":
        return render(
            request,
            "login.html",
            _auth_context(
                next=next,
                error="No account found. Create one first.",
                mode="email",
                email=email,
            ),
            status_code=404,
        )
    if status == "unverified":
        dev_link = (
            account_service.build_auth_url(dev_token, "signup_verify") if dev_token else None
        )
        return render(
            request,
            "auth_email_sent.html",
            _auth_context(
                email=account_service.normalize_email(email),
                purpose="signup",
                dev_link=dev_link,
                message="Your email is not verified yet. We sent a new confirmation link.",
            ),
        )

    dev_link = (
        account_service.build_auth_url(dev_token, "login_magic") if dev_token else None
    )
    return render(
        request,
        "auth_email_sent.html",
        _auth_context(
            email=account_service.normalize_email(email),
            purpose="login",
            dev_link=dev_link,
        ),
    )


@router.get("/auth/verify")
def verify_email(
    request: Request,
    token: str,
    purpose: str = "signup_verify",
    db: Session = Depends(get_db),
):
    if purpose not in ("signup_verify", "login_magic"):
        return RedirectResponse(url="/login?error=invalid_link", status_code=302)

    account = account_service.verify_token(db, token, purpose)
    if not account:
        return render(
            request,
            "login.html",
            _auth_context(
                error="This link is invalid or has expired. Request a new one.",
                mode="email",
            ),
            status_code=400,
        )

    account_service.ensure_profile(db, account)
    login_user(request, account_id=account.id, email=account.email)
    user = onboarding_service.get_or_create_user(db, account_id=account.id)
    return RedirectResponse(url=post_auth_path(user), status_code=302)


@router.get("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse(url="/", status_code=302)