"""MatchForge FastAPI entrypoint.

Run (with venv active):
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.capacity_handlers import capacity_aware_http_handler

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path("data/uploads").mkdir(parents=True, exist_ok=True)

    # Trend-aware threat intel: refresh the scam-tactic brief from X (via
    # Grok x_search) shortly after boot, then re-check daily; the service
    # only re-fetches when the cached brief exceeds THREAT_INTEL_REFRESH_DAYS.
    scheduler = None
    if settings.threat_intel_enabled and settings.xai_api_key:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        from app.services.threat_intel_service import refresh_if_stale

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            refresh_if_stale, "interval", days=1, id="threat_intel_refresh"
        )
        scheduler.add_job(refresh_if_stale, id="threat_intel_boot")
        scheduler.start()

    yield

    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Screenshot-first, privacy-first dating intelligence toolbox.",
    lifespan=lifespan,
)

app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
app.add_exception_handler(HTTPException, capacity_aware_http_handler)

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