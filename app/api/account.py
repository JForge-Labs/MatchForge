"""Account settings and deletion."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_account_id, logout_user, require_auth
from app.core.db import get_db
from app.services import account_service

router = APIRouter(prefix="/account", tags=["account"])


class DeleteAccountIn(BaseModel):
    confirm: str


@router.post("/delete")
def delete_account(
    body: DeleteAccountIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """Permanently delete the signed-in account and all associated data."""
    require_auth(request)
    if body.confirm.strip().upper() != "DELETE":
        raise HTTPException(400, detail="Type DELETE to confirm account removal")

    account_id = get_account_id(request)
    if not account_id:
        raise HTTPException(401, "Not signed in")

    if not account_service.delete_account(db, account_id):
        raise HTTPException(404, "Account not found")

    logout_user(request)
    return JSONResponse({"ok": True, "redirect": "/"})