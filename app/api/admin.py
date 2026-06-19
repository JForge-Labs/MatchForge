"""Admin dashboard — operators only."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.admin import is_admin, require_admin
from app.core.auth import is_authenticated, redirect_if_unauthenticated
from app.core.db import get_db
from app.models.account import Account
from app.services import admin_service, affiliate_service, credit_service
from app.utils.templates import render

router = APIRouter(prefix="/admin", tags=["admin"])


class GrantTokensIn(BaseModel):
    account_id: int
    amount: int = Field(..., ge=1, le=10000)
    note: str | None = None


class MarkPaidIn(BaseModel):
    ids: list[int] = Field(..., min_length=1)
    payout_note: str | None = Field(None, max_length=256)


class CreateAffiliateIn(BaseModel):
    slug: str = Field(..., min_length=2, max_length=63)
    name: str = Field(..., min_length=1, max_length=128)
    contact_email: str = Field(..., min_length=3, max_length=320)
    commission_rate_pct: float = Field(15.0, ge=0.1, le=100)
    notes: str | None = Field(None, max_length=2000)


@router.get("", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    if redirect := redirect_if_unauthenticated(request):
        return redirect
    if not is_admin(request, db):
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
    require_admin(request, db)
    return admin_service.dashboard_stats(db)


@router.get("/api/accounts")
def admin_accounts_api(request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    return {"accounts": admin_service.list_accounts(db)}


@router.get("/api/transactions")
def admin_transactions_api(request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    return {"transactions": admin_service.list_transactions(db)}


@router.post("/api/grant-tokens")
def admin_grant_tokens(
    body: GrantTokensIn,
    request: Request,
    db: Session = Depends(get_db),
):
    require_admin(request, db)
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


@router.get("/affiliates", response_class=HTMLResponse)
def admin_affiliates_page(
    request: Request,
    db: Session = Depends(get_db),
    affiliate_id: int | None = Query(None),
    status: str | None = Query(None),
):
    if redirect := redirect_if_unauthenticated(request):
        return redirect
    if not is_admin(request, db):
        return RedirectResponse("/dashboard", status_code=302)

    affiliates = affiliate_service.list_affiliates_with_stats(db, include_test=False)
    commissions = affiliate_service.list_commissions(
        db,
        affiliate_id=affiliate_id,
        status=status,
        limit=80,
    )
    test_affiliate_count = affiliate_service.count_test_affiliates(db)
    return render(
        request,
        "admin/affiliates.html",
        {
            "authed": is_authenticated(request),
            "active": None,
            "affiliates": affiliates,
            "commissions": commissions,
            "filter_affiliate_id": affiliate_id,
            "filter_status": status or "",
            "test_affiliate_count": test_affiliate_count,
        },
        db=db,
    )


@router.get("/api/affiliates")
def admin_affiliates_api(request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    return {"affiliates": affiliate_service.list_affiliates_with_stats(db)}


@router.get("/api/affiliate-commissions")
def admin_affiliate_commissions_api(
    request: Request,
    db: Session = Depends(get_db),
    affiliate_id: int | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    require_admin(request, db)
    return {
        "commissions": affiliate_service.list_commissions(
            db,
            affiliate_id=affiliate_id,
            status=status,
            limit=limit,
        )
    }


@router.post("/api/affiliate-commissions/mark-paid")
def admin_mark_commissions_paid(
    body: MarkPaidIn,
    request: Request,
    db: Session = Depends(get_db),
):
    require_admin(request, db)
    count = affiliate_service.mark_commissions_paid(
        db, body.ids, payout_note=body.payout_note
    )
    db.commit()
    return {"ok": True, "marked_paid": count}


@router.post("/api/affiliates")
def admin_create_affiliate(
    body: CreateAffiliateIn,
    request: Request,
    db: Session = Depends(get_db),
):
    require_admin(request, db)
    try:
        affiliate = affiliate_service.create_affiliate(
            db,
            slug=body.slug,
            name=body.name,
            contact_email=body.contact_email,
            commission_rate=body.commission_rate_pct / 100,
            notes=body.notes,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    stats = affiliate_service.affiliate_stats(db, affiliate)
    return {"ok": True, "affiliate": stats}


@router.post("/api/affiliates/cleanup-test")
def admin_cleanup_test_affiliates(request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    deleted = affiliate_service.delete_test_affiliates(db)
    db.commit()
    return {"ok": True, "deleted": deleted}