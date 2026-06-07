"""HTTP handlers for at-capacity / surge traffic responses."""
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exception_handlers import http_exception_handler

from app.core.auth import is_authenticated
from app.utils.templates import render
from app.utils.ui_context import ui_context


def _is_capacity_error(exc: HTTPException) -> bool:
    return (
        exc.status_code == 503
        and isinstance(exc.detail, dict)
        and exc.detail.get("error") == "capacity"
    )


def _prefers_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return False
    return True


async def capacity_aware_http_handler(request: Request, exc: HTTPException):
    if not _is_capacity_error(exc):
        return await http_exception_handler(request, exc)

    detail = exc.detail
    retry = str(detail.get("retry_after_seconds", 120))
    headers = {"Retry-After": retry}

    if _prefers_html(request):
        ctx = ui_context(
            authed=is_authenticated(request),
            headline=detail.get("headline"),
            message=detail.get("message"),
            retry_after_seconds=detail.get("retry_after_seconds"),
        )
        return render(
            request,
            "at_capacity.html",
            ctx,
            status_code=503,
            headers=headers,
        )

    return JSONResponse(status_code=503, content=detail, headers=headers)