"""Dashboard and percolated shortlist endpoints."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.core.db import get_db
from app.models.profile import Profile, Ranking
from app.schemas.profile import PercolatedDashboard
from app.services import onboarding_service

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="templates")


@router.get("/dashboard/percolated", response_model=PercolatedDashboard)
def percolated_shortlist(db: Session = Depends(get_db)):
    """Return ranked shortlist sorted by percolation priority."""
    user = onboarding_service.get_or_create_user(db)
    pref = onboarding_service.get_user_preference(db)
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


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_ui(request: Request, db: Session = Depends(get_db)):
    """HTML dashboard — redirects to onboarding if not complete."""
    user = onboarding_service.get_or_create_user(db)
    if not user.onboarding_complete:
        return RedirectResponse(url="/onboarding", status_code=302)

    data = percolated_shortlist(db)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "total": data.total_profiles,
            "shortlist": data.shortlist,
            "preference": data.preference_vector,
            "user": user,
        },
    )