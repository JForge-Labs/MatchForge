"""Read-only affiliate partner dashboard (magic-link access)."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services import affiliate_service
from app.utils.templates import render

router = APIRouter(tags=["partner"])


@router.get("/partner", response_class=HTMLResponse)
def partner_dashboard(
    request: Request,
    token: str = "",
    db: Session = Depends(get_db),
):
    affiliate_id = affiliate_service.resolve_partner_token(token)
    if not affiliate_id:
        return render(
            request,
            "partner/expired.html",
            {"authed": False},
            status_code=403,
        )

    affiliate = affiliate_service.get_affiliate_by_id(db, affiliate_id)
    if not affiliate or not affiliate.is_active:
        return render(
            request,
            "partner/expired.html",
            {"authed": False},
            status_code=404,
        )

    ctx = affiliate_service.partner_dashboard_context(db, affiliate)
    return render(
        request,
        "partner/dashboard.html",
        {
            "authed": False,
            **ctx,
        },
    )
