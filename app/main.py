"""MatchForge FastAPI entrypoint.

Run (with venv active):
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api import auth, billing, dashboard, health, onboarding, pages, profiles, toolbox
from app.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path("data/uploads").mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Screenshot-first, privacy-first dating intelligence toolbox.",
    lifespan=lifespan,
)

app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

app.include_router(health.router)
app.include_router(billing.router)
app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(toolbox.router)
app.include_router(profiles.router)
app.include_router(dashboard.router)

static_dir = Path("static")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")