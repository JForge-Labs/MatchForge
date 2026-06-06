"""Token balance and referral program endpoints."""
from fastapi import APIRouter, Depends, Request

from app.core.auth import get_account_id, require_auth
from app.core.db import get_db
from app.services import credit_service, referral_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/billing", tags=["billing"])


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