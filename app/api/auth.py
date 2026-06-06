"""Login and logout endpoints."""
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.auth import is_authenticated, login_user, logout_user, verify_password

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/dashboard", error: str | None = None):
    if is_authenticated(request):
        return RedirectResponse(url=next, status_code=302)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"next": next, "error": error, "authed": False},
    )


@router.post("/login")
def login_submit(
    request: Request,
    password: str = Form(...),
    next: str = Form("/dashboard"),
):
    if not verify_password(password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "next": next,
                "error": "Incorrect password. Try again.",
                "authed": False,
            },
            status_code=401,
        )
    login_user(request)
    if not next.startswith("/"):
        next = "/dashboard"
    return RedirectResponse(url=next, status_code=302)


@router.get("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse(url="/", status_code=302)