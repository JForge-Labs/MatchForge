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
from app.services import account_service, capacity_service, email_service
from app.services import affiliate_service, onboarding_service
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


@router.get("/join/{link_code}")
def affiliate_join(link_code: str, db: Session = Depends(get_db)):
    """Opaque affiliate entry — sets attribution cookie and redirects to signup."""
    affiliate = affiliate_service.get_affiliate_by_ref(db, link_code)
    if not affiliate or not affiliate_service.affiliates_enabled():
        return RedirectResponse(url="/signup", status_code=302)
    ref = affiliate_service.affiliate_join_ref(db, affiliate)
    db.commit()
    response = RedirectResponse(url="/signup", status_code=302)
    response.set_cookie(
        key=affiliate_service.AFFILIATE_COOKIE,
        value=ref,
        max_age=affiliate_service.AFFILIATE_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/signup", response_class=HTMLResponse)
def signup_page(
    request: Request,
    db: Session = Depends(get_db),
    error: str | None = None,
    ref: str | None = None,
    aff: str | None = None,
):
    if is_authenticated(request):
        account_id = get_account_id(request)
        user = onboarding_service.get_or_create_user(db, account_id=account_id)
        return RedirectResponse(url=post_auth_path(user), status_code=302)

    affiliate_ref = ""
    if affiliate_service.affiliates_enabled():
        if aff and affiliate_service.get_affiliate_by_ref(db, aff):
            affiliate = affiliate_service.get_affiliate_by_ref(db, aff)
            affiliate_ref = affiliate_service.affiliate_join_ref(db, affiliate)
            db.commit()
        elif request.cookies.get(affiliate_service.AFFILIATE_COOKIE):
            cookie_ref = request.cookies.get(affiliate_service.AFFILIATE_COOKIE, "")
            if affiliate_service.get_affiliate_by_ref(db, cookie_ref):
                affiliate_ref = cookie_ref.strip()

    og_extra = {}
    if ref:
        og_extra = {
            "og_title": REFERRAL_OG_TITLE,
            "og_description": REFERRAL_OG_DESCRIPTION,
            "twitter_title": REFERRAL_OG_TITLE,
            "twitter_description": REFERRAL_OG_DESCRIPTION,
            "og_url": f"{get_settings().app_url.rstrip('/')}/signup?ref={ref}",
        }

    response = render(
        request,
        "signup.html",
        _auth_context(
            error=error,
            referral_code=ref or "",
            affiliate_ref=affiliate_ref,
            referral_og_title=REFERRAL_OG_TITLE,
            referral_og_description=REFERRAL_OG_DESCRIPTION,
            **og_extra,
        ),
    )
    if affiliate_ref:
        response.set_cookie(
            key=affiliate_service.AFFILIATE_COOKIE,
            value=affiliate_ref,
            max_age=affiliate_service.AFFILIATE_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
        )
    return response


@router.post("/signup")
def signup_submit(
    request: Request,
    email: str = Form(...),
    referral_code: str = Form(""),
    affiliate_ref: str = Form(""),
    db: Session = Depends(get_db),
):
    capacity_service.raise_if_overloaded(signup=True)
    ref = affiliate_ref.strip() or request.cookies.get(
        affiliate_service.AFFILIATE_COOKIE, ""
    )
    status, dev_token = account_service.request_signup(
        db,
        email,
        referral_code=referral_code or None,
        affiliate_ref=ref or None,
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