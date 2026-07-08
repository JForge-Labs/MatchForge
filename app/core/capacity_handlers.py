"""HTTP handlers for at-capacity, not-found, and server-error responses."""
import logging

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exception_handlers import http_exception_handler

from app.core.auth import is_authenticated
from app.utils.templates import render
from app.utils.ui_context import ui_context

logger = logging.getLogger(__name__)


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
    if _is_capacity_error(exc):
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

    if exc.status_code in (404, 405) and _prefers_html(request):
        return render(
            request,
            "error.html",
            {
                "authed": is_authenticated(request),
                "active": None,
                "error_code": exc.status_code,
                "error_headline": "Page not found",
                "error_message": (
                    "That page doesn't exist or has moved. "
                    "Your profiles and analyses are safe on your dashboard."
                ),
            },
            status_code=exc.status_code,
        )

    return await http_exception_handler(request, exc)


async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled error on %s %s", request.method, request.url.path
    )
    if _prefers_html(request):
        return render(
            request,
            "error.html",
            {
                "authed": is_authenticated(request),
                "active": None,
                "error_code": 500,
                "error_headline": "Something went wrong",
                "error_message": (
                    "An unexpected error occurred on our side — nothing was "
                    "charged for this request. Please try again."
                ),
            },
            status_code=500,
        )
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our side. Please try again."},
    )