"""Token balance, Stripe checkout, and referral program endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.auth import get_account_id, is_authenticated, require_auth
from app.core.config import get_settings
from app.core.db import get_db
from app.models.account import Account
from app.schemas.billing import CheckoutIn
from app.services import credit_service, referral_service, stripe_service
from app.utils.templates import render

router = APIRouter(prefix="/billing", tags=["billing"])
settings = get_settings()


@router.get("/balance")
def token_balance(request: Request, db: Session = Depends(get_db)):
    require_auth(request)
    account_id = get_account_id(request)
    return {"balance": credit_service.get_balance(db, account_id)}


@router.get("/referrals")
def referral_program(request: Request, db: Session = Depends(get_db)):
    """Referral link, stats, and lock-in reward info for the logged-in user."""
    require_auth(request)
    account_id = get_account_id(request)
    return referral_service.get_referral_stats(db, account_id)


@router.get("", response_class=HTMLResponse)
def billing_page(request: Request, db: Session = Depends(get_db)):
    require_auth(request)
    account_id = get_account_id(request)
    return render(
        request,
        "billing.html",
        {
            "active": "billing",
            "authed": True,
            "balance": credit_service.get_balance(db, account_id),
            "billing_enabled": credit_service.billing_enabled(),
            "stripe_configured": stripe_service.stripe_configured(),
            "stripe_publishable_key": settings.stripe_publishable_key,
            "min_topup_usd": settings.min_topup_usd,
            "default_topup_usd": settings.default_topup_usd,
            "tokens_per_usd": settings.tokens_per_usd,
        },
        db=db,
    )


@router.post("/checkout")
def start_checkout(
    body: CheckoutIn,
    request: Request,
    db: Session = Depends(get_db),
):
    require_auth(request)
    account_id = get_account_id(request)
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(404, "Account not found")
    return stripe_service.create_checkout_session(db, account, body.amount_usd)


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    return stripe_service.handle_webhook(db, payload, signature)


@router.get("/success", response_class=HTMLResponse)
def billing_success(
    request: Request,
    session_id: str | None = None,
    db: Session = Depends(get_db),
):
    require_auth(request)
    account_id = get_account_id(request)
    if session_id and credit_service.billing_enabled():
        stripe_service.reconcile_checkout_session(db, session_id, account_id)
    return render(
        request,
        "billing_success.html",
        {
            "active": "billing",
            "authed": True,
            "balance": credit_service.get_balance(db, account_id),
        },
        db=db,
    )


@router.get("/cancel", response_class=HTMLResponse)
def billing_cancel(request: Request, db: Session = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/login?next=/billing", status_code=303)
    return render(
        request,
        "billing_cancel.html",
        {"active": "settings", "authed": True},
        db=db,
    )