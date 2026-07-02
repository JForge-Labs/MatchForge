"""Public pages: landing, home, shared analysis, and verification badge views."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.auth import is_authenticated
from app.core.db import get_db
from app.models.profile import Profile
from app.services import capacity_service, share_service
from app.utils.badge_image import render_verify_badge
from app.utils.templates import render

router = APIRouter(tags=["pages"])


def _load_shared_verification(db: Session, token: str) -> tuple[Profile, dict] | None:
    parsed = share_service.verify_verify_token(token)
    if not parsed:
        return None
    account_id, profile_id = parsed
    profile = (
        db.query(Profile)
        .filter(Profile.id == profile_id, Profile.account_id == account_id)
        .first()
    )
    if not profile:
        return None
    report = profile.x_verification or {}
    # Public rendering requires the owner's explicit opt-in
    if not report.get("verdict") or not report.get("share_enabled"):
        return None
    return profile, report


@router.get("/verify/{token}", response_class=HTMLResponse)
def shared_verification(request: Request, token: str, db: Session = Depends(get_db)):
    """Public X-verification report — opt-in share, public X data only."""
    loaded = _load_shared_verification(db, token)
    share_url = share_service.build_verify_share_url(token)
    if not loaded:
        return render(
            request,
            "share_expired.html",
            {
                "authed": is_authenticated(request),
                "active": None,
                "share_url": share_url,
                "signup_url": "/signup",
                "referral_url": None,
                "og_title": "Verification link expired — MatchForge",
                "og_description": "This X-verification report is no longer available.",
            },
        )
    _profile, report = loaded
    score = report.get("x_social_proof_score")
    title = f"@{report['handle']} — X-verified by MatchForge"
    description = (
        f"X Social Proof {score:.0f}/100 · {report.get('verdict', '').replace('_', ' ')}"
        if score is not None
        else report.get("one_line_summary", "AI dating-safety verification")
    )
    return render(
        request,
        "verify_share.html",
        {
            "authed": is_authenticated(request),
            "active": None,
            "report": report,
            "share_url": share_url,
            "badge_url": f"{share_url}/badge.png",
            "og_title": title,
            "og_description": description,
            "og_url": share_url,
            "og_image": f"{share_url}/badge.png",
            "twitter_title": title,
            "twitter_description": description,
        },
    )


@router.get("/verify/{token}/badge.png", include_in_schema=False)
def shared_verification_badge(token: str, db: Session = Depends(get_db)):
    """OG card image for the public verification report."""
    loaded = _load_shared_verification(db, token)
    if not loaded:
        raise HTTPException(404, "Verification not found")
    _profile, report = loaded
    png = render_verify_badge(
        handle=report["handle"],
        score=report.get("x_social_proof_score"),
        verdict=report.get("verdict", "inconclusive"),
        summary=report.get("one_line_summary", ""),
    )
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/share/{token}", response_class=HTMLResponse)
def shared_analysis(request: Request, token: str, db: Session = Depends(get_db)):
    """Public, token-gated view of a shared analysis (includes referrer signup link)."""
    kind, data = share_service.resolve_share_page(
        db, token, user_agent=request.headers.get("user-agent")
    )
    template = "share.html" if kind == "active" else "share_expired.html"
    return render(
        request,
        template,
        {"authed": is_authenticated(request), "active": None, **data},
    )


@router.get("/favicon.ico", include_in_schema=False)
def favicon_redirect():
    return RedirectResponse(url="/static/favicon.svg", status_code=301)


@router.get("/apple-touch-icon.png", include_in_schema=False)
def apple_touch_icon():
    return RedirectResponse(url="/static/icons/apple-touch-icon.png", status_code=301)


@router.get("/at-capacity", response_class=HTMLResponse)
def at_capacity_page(request: Request):
    detail = capacity_service.capacity_detail()
    return render(
        request,
        "at_capacity.html",
        {
            "authed": is_authenticated(request),
            "headline": detail["headline"],
            "message": detail["message"],
            "retry_after_seconds": detail["retry_after_seconds"],
        },
    )


@router.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return render(
        request,
        "landing.html",
        {"authed": is_authenticated(request), "active": None},
    )