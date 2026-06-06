"""Health / readiness endpoints."""
from fastapi import APIRouter

from app.core.config import get_settings
from app.core import db
from app.services import llm_service

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@router.get("/health/db")
def health_db():
    try:
        db.ping()
        return {"database": "ok"}
    except Exception as exc:
        return {"database": "error", "detail": str(exc)}


@router.get("/health/llm")
async def health_llm():
    return await llm_service.health_check()


@router.get("/health/ollama")
async def health_ollama_legacy():
    """Deprecated — use /health/llm."""
    result = await llm_service.health_check()
    if result.get("llm") == "ok":
        return {"ollama": "deprecated", "use": "/health/llm", **result}
    return {"ollama": "error", "use": "/health/llm", **result}