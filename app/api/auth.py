"""Signup, email verification, login, and logout."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.auth import is_authenticated, login_user, logout_user, verify_password
from app.core.config import get_settings
from app.core.db import get_db
from app.services import account_service, email_service

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="templates")


def _auth_context(**extra):
    settings = get_settings()
    return {
        "authed": False,
        "smtp_configured": email_service.smtp_configured(),
        "app_env": settings.app_env,
        **extra,
    }


@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request, error: str | None = None):
    if is_authenticated(request):
        return RedirectResponse(url="/onboarding", status_code=302)
    return templates.TemplateResponse(
        request,
        "signup.html",
        _auth_context(error=error),
    )


@router.post("/signup")
def signup_submit(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    status, dev_token = account_service.request_signup(db, email)
    if status == "invalid":
        return templates.TemplateResponse(
            request,
            "signup.html",
            _auth_context(error="Enter a valid email address."),
            status_code=400,
        )
    if status == "exists":
        return templates.TemplateResponse(
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
    return templates.TemplateResponse(
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
    return templates.TemplateResponse(
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
            return templates.TemplateResponse(
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
        if not next.startswith("/"):
            next = "/dashboard"
        return RedirectResponse(url=next, status_code=302)

    status, dev_token = account_service.request_login_link(db, email)
    if status == "invalid":
        return templates.TemplateResponse(
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
        return templates.TemplateResponse(
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
        return templates.TemplateResponse(
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
    return templates.TemplateResponse(
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
        return templates.TemplateResponse(
            request,
            "login.html",
            _auth_context(
                error="This link is invalid or has expired. Request a new one.",
                mode="email",
            ),
            status_code=400,
        )

    profile = account_service.ensure_profile(db, account)
    login_user(request, account_id=account.id, email=account.email)
    target = "/onboarding" if not profile.onboarding_complete else "/dashboard"
    return RedirectResponse(url=target, status_code=302)


@router.get("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse(url="/", status_code=302)