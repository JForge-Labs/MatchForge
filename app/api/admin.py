"""Admin dashboard — operators only."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.admin import is_admin, require_admin
from app.core.auth import is_authenticated, redirect_if_unauthenticated
from app.core.db import get_db
from app.models.account import Account
from app.services import admin_service, credit_service
from app.utils.templates import render

router = APIRouter(prefix="/admin", tags=["admin"])


class GrantTokensIn(BaseModel):
    account_id: int
    amount: int = Field(..., ge=1, le=10000)
    note: str | None = None


@router.get("", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    if redirect := redirect_if_unauthenticated(request):
        return redirect
    if not is_admin(request):
        return RedirectResponse("/dashboard", status_code=302)

    stats = admin_service.dashboard_stats(db)
    accounts = admin_service.list_accounts(db, limit=50)
    transactions = admin_service.list_transactions(db, limit=40)
    return render(
        request,
        "admin/dashboard.html",
        {
            "authed": is_authenticated(request),
            "active": None,
            "stats": stats,
            "accounts": accounts,
            "transactions": transactions,
        },
        db=db,
    )


@router.get("/api/stats")
def admin_stats_api(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    return admin_service.dashboard_stats(db)


@router.get("/api/accounts")
def admin_accounts_api(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    return {"accounts": admin_service.list_accounts(db)}


@router.get("/api/transactions")
def admin_transactions_api(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    return {"transactions": admin_service.list_transactions(db)}


@router.post("/api/grant-tokens")
def admin_grant_tokens(
    body: GrantTokensIn,
    request: Request,
    db: Session = Depends(get_db),
):
    require_admin(request)
    account = db.query(Account).filter(Account.id == body.account_id).first()
    if not account:
        raise HTTPException(404, "Account not found")

    operator = request.session.get("account_email") or "admin"
    note = body.note or f"Granted by {operator}"
    balance = credit_service.grant_tokens(
        db,
        body.account_id,
        body.amount,
        "admin_grant",
        note=note,
        metadata={"granted_by": operator},
    )
    db.commit()
    return {"ok": True, "account_id": body.account_id, "balance": balance}