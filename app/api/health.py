"""Health / readiness endpoints."""
import httpx
from fastapi import APIRouter

from app.core.config import get_settings
from app.core import db

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


@router.get("/health/ollama")
async def health_ollama():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
        return {
            "ollama": "ok",
            "models": models,
            "vision_model": settings.vision_model,
            "text_model": settings.text_model,
        }
    except Exception as exc:
        return {"ollama": "error", "detail": str(exc)}
