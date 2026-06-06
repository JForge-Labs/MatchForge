"""Dashboard and percolated shortlist endpoints."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.core.auth import (
    get_account_id,
    is_authenticated,
    redirect_if_unauthenticated,
    require_auth,
)
from app.core.db import get_db
from app.models.profile import Profile, Ranking
from app.schemas.profile import PercolatedDashboard
from app.services import onboarding_service
from app.utils.profile_labels import format_user_badge, match_profile_label

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="templates")


def _percolated_data(db: Session, account_id: int | None = None) -> PercolatedDashboard:
    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    pref = onboarding_service.get_user_preference(db, account_id=account_id)
    rankings = (
        db.query(Ranking)
        .options(
            joinedload(Ranking.profile).joinedload(Profile.social_enrichments)
        )
        .order_by(Ranking.percolation_priority.desc())
        .limit(50)
        .all()
    )
    total = db.query(Profile).count()
    return PercolatedDashboard(
        total_profiles=total,
        shortlist=rankings,
        preference_vector=pref,
        user_gender=user.gender,
        user_intentions=user.intentions or [],
        onboarding_complete=user.onboarding_complete,
    )


@router.get("/dashboard/percolated", response_model=PercolatedDashboard)
def percolated_shortlist(request: Request, db: Session = Depends(get_db)):
    """Return ranked shortlist sorted by percolation priority."""
    require_auth(request)
    return _percolated_data(db, account_id=get_account_id(request))


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_ui(request: Request, db: Session = Depends(get_db)):
    """HTML dashboard — redirects to onboarding if not complete."""
    if redirect := redirect_if_unauthenticated(request):
        return redirect

    account_id = get_account_id(request)
    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    if not user.onboarding_complete:
        return RedirectResponse(url="/onboarding", status_code=302)

    data = _percolated_data(db, account_id=account_id)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "total": data.total_profiles,
            "shortlist": data.shortlist,
            "preference": data.preference_vector,
            "match_profile_label": match_profile_label(
                gender=user.gender,
                preferred_genders=user.preferred_genders,
                goals=user.intentions,
            ),
            "user_badge": format_user_badge(
                gender=user.gender,
                preferred_genders=user.preferred_genders,
                goals=user.intentions,
            ),
            "user": user,
            "authed": is_authenticated(request),
            "active": "dashboard",
        },
    )