"""Dashboard and percolated shortlist endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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
from app.services import (
    credit_service,
    onboarding_service,
    profile_merge_service,
    referral_service,
)
from app.utils.legal import policies_accepted
from app.utils.profile_labels import format_user_badge, match_profile_label
from app.utils.profile_tokens import profile_tokens_spent
from app.utils.templates import render
from app.utils.trust_display import trust_card_context
from app.services.model_router import route

router = APIRouter(tags=["dashboard"])


def _shortlist_rankings(
    db: Session, account_id: int | None = None
) -> tuple[list[Ranking], int]:
    profile_filter = []
    if account_id is not None:
        profile_filter.append(Profile.account_id == account_id)

    if account_id is not None:
        profile_merge_service.merge_duplicate_profiles(db, account_id)

    rankings = (
        db.query(Ranking)
        .join(Profile, Ranking.profile_id == Profile.id)
        .options(
            joinedload(Ranking.profile).joinedload(Profile.social_enrichments),
            joinedload(Ranking.profile).joinedload(Profile.evidence),
        )
        .filter(*profile_filter)
        .order_by(Ranking.percolation_priority.desc())
        .limit(100)
        .all()
    )
    rankings = profile_merge_service.dedupe_shortlist_rankings(rankings)[:50]
    total = db.query(Profile).filter(*profile_filter).count()
    return rankings, total


def _percolated_data(db: Session, account_id: int | None = None) -> PercolatedDashboard:
    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    pref = onboarding_service.get_user_preference(db, account_id=account_id)
    rankings, total = _shortlist_rankings(db, account_id=account_id)
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


@router.get("/dashboard/cards/{profile_id}", response_class=HTMLResponse)
def profile_card_fragment(
    request: Request, profile_id: int, db: Session = Depends(get_db)
):
    """Server-rendered card fragment for in-place refresh (no full reload)."""
    require_auth(request)
    account_id = get_account_id(request)
    ranking = (
        db.query(Ranking)
        .join(Profile, Ranking.profile_id == Profile.id)
        .options(
            joinedload(Ranking.profile).joinedload(Profile.social_enrichments),
            joinedload(Ranking.profile).joinedload(Profile.evidence),
        )
        .filter(Profile.id == profile_id, Profile.account_id == account_id)
        .first()
    )
    if not ranking:
        raise HTTPException(404, "Profile not found")
    pref = onboarding_service.get_user_preference(db, account_id=account_id)
    item = {
        "ranking": ranking,
        "trust": trust_card_context(ranking.profile, ranking, preference=pref),
        "tokens_spent": profile_tokens_spent(ranking.profile, db),
    }
    return render(
        request,
        "partials/profile_card.html",
        {
            "item": item,
            "x_verify_cost": route("x_verify").token_cost,
            "agent_est_min": (
                route("profile_agent").token_cost + route("rank_refresh").token_cost
            ),
            "agent_image_cost": route("profile_agent_image").token_cost,
        },
        db=db,
    )


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_ui(request: Request, db: Session = Depends(get_db)):
    """HTML dashboard — redirects to onboarding if not complete."""
    if redirect := redirect_if_unauthenticated(request):
        return redirect

    account_id = get_account_id(request)
    user = onboarding_service.get_or_create_user(db, account_id=account_id)
    if not policies_accepted(user):
        return RedirectResponse(url="/legal/accept", status_code=302)
    if not user.onboarding_complete:
        return RedirectResponse(url="/onboarding", status_code=302)

    pref = onboarding_service.get_user_preference(db, account_id=account_id)
    rankings, total = _shortlist_rankings(db, account_id=account_id)
    referrals = referral_service.get_referral_stats(db, account_id)
    agent_est = (
        route("profile_agent").token_cost
        + route("rank_refresh").token_cost
    )
    cards = [
        {
            "ranking": r,
            "trust": trust_card_context(r.profile, r, preference=pref),
            "tokens_spent": profile_tokens_spent(r.profile, db),
        }
        for r in rankings
    ]
    return render(
        request,
        "dashboard.html",
        {
            "total": total,
            "shortlist": rankings,
            "cards": cards,
            "preference": pref,
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
            "token_balance": credit_service.get_balance(db, account_id),
            "billing_enabled": credit_service.billing_enabled(),
            "referrals": referrals,
            "agent_est_min": agent_est,
            "agent_image_cost": route("profile_agent_image").token_cost,
            "x_verify_cost": route("x_verify").token_cost,
            "upload_cost": route("profile_screenshot").token_cost,
            "deep_vet_cost": route("deep_vet").token_cost,
            "authed": is_authenticated(request),
            "active": "dashboard",
        },
        db=db,
    )