"""MatchForge FastAPI entrypoint.

Run (with venv active):
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
import logging
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.core.capacity_handlers import (
    capacity_aware_http_handler,
    unhandled_exception_handler,
)

from app.api import (
    account,
    admin,
    auth,
    billing,
    dashboard,
    health,
    legal,
    onboarding,
    pages,
    partner,
    profiles,
    toolbox,
    x_verify,
)
from app.core.config import get_settings

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
_access_logger = logging.getLogger("matchforge.request")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path("data/uploads").mkdir(parents=True, exist_ok=True)

    # Trend-aware threat intel: refresh the scam-tactic brief from X (via
    # Grok x_search) shortly after boot, then re-check daily; the service
    # only re-fetches when the cached brief exceeds THREAT_INTEL_REFRESH_DAYS.
    scheduler = None
    if settings.threat_intel_enabled and settings.xai_api_key:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            from app.services.threat_intel_service import refresh_if_stale

            scheduler = AsyncIOScheduler()
            scheduler.add_job(
                refresh_if_stale, "interval", days=1, id="threat_intel_refresh"
            )
            scheduler.add_job(refresh_if_stale, id="threat_intel_boot")
            scheduler.start()
        except Exception as exc:  # never block app boot on the intel job
            import logging

            logging.getLogger(__name__).warning(
                "Threat intel scheduler unavailable: %s", exc
            )
            scheduler = None

    yield

    if scheduler:
        scheduler.shutdown(wait=False)


_is_prod = settings.app_env == "production"

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Screenshot-first, privacy-first dating intelligence toolbox.",
    lifespan=lifespan,
    # The interactive API docs enumerate every endpoint of a billed product —
    # keep them off the public internet (staging is public too).
    docs_url="/docs" if settings.app_env == "development" else None,
    redoc_url="/redoc" if settings.app_env == "development" else None,
    openapi_url="/openapi.json" if settings.app_env == "development" else None,
)


class HeadToGetMiddleware:
    """Answer HEAD requests (uptime monitors, crawlers) as body-less GETs."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "HEAD":
            async def send_without_body(message):
                if message["type"] == "http.response.body":
                    message = {**message, "body": b""}
                await send(message)

            await self.app(dict(scope, method="GET"), receive, send_without_body)
            return
        await self.app(scope, receive, send)


_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "font-src 'self'; "
    "img-src 'self' data: https:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self' https://checkout.stripe.com"
)


@app.middleware("http")
async def request_id_and_timing(request, call_next):
    """Tag every request so 'my upload failed' is reconstructable from logs."""
    request_id = secrets.token_hex(6)
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers.setdefault("X-Request-ID", request_id)
    if not request.url.path.startswith("/static"):
        _access_logger.info(
            "%s %s -> %s %.0fms rid=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
    return response


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    headers = response.headers
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "DENY")
    headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    headers.setdefault("Content-Security-Policy", _CSP)
    if _is_prod:
        headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


app.add_middleware(HeadToGetMiddleware)
app.add_middleware(
    SessionMiddleware, secret_key=settings.secret_key, https_only=_is_prod
)
app.add_exception_handler(StarletteHTTPException, capacity_aware_http_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(health.router)
app.include_router(account.router)
app.include_router(admin.router)
app.include_router(billing.router)
app.include_router(pages.router)
app.include_router(legal.router)
app.include_router(auth.router)
app.include_router(partner.router)
app.include_router(onboarding.router)
app.include_router(toolbox.router)
app.include_router(profiles.router)
app.include_router(x_verify.router)
app.include_router(dashboard.router)

static_dir = Path("static")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")