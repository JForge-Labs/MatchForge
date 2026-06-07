"""Lightweight capacity gates for surge traffic (foundational — no Redis yet)."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import HTTPException

from app.core.config import get_settings

OVERLOAD_HEADLINE = "We're scaling up for you"
OVERLOAD_MESSAGE = (
    "MatchForge is experiencing a large influx of new users right now. "
    "We're actively adding capacity — your screenshots and account are safe. "
    "Please try again in a few minutes."
)
OVERLOAD_SIGNUP_MESSAGE = (
    "Signups are temporarily paused while we scale infrastructure. "
    "Please check back shortly — we're working on it."
)

_slot_lock = asyncio.Lock()
_heavy_inflight = 0


def _heavy_limit() -> int:
    return max(1, get_settings().capacity_max_concurrent_uploads)


def overload_mode_enabled() -> bool:
    return get_settings().overload_mode


def heavy_slots_in_use() -> int:
    return _heavy_inflight


def capacity_detail(*, signup: bool = False) -> dict:
    settings = get_settings()
    return {
        "error": "capacity",
        "headline": OVERLOAD_HEADLINE,
        "message": OVERLOAD_SIGNUP_MESSAGE if signup else OVERLOAD_MESSAGE,
        "retry_after_seconds": settings.capacity_retry_after_seconds,
    }


def raise_if_overloaded(*, signup: bool = False) -> None:
    """Manual kill-switch (OVERLOAD_MODE=true). Saturation is handled by heavy_work_slot."""
    if overload_mode_enabled():
        raise HTTPException(status_code=503, detail=capacity_detail(signup=signup))


@asynccontextmanager
async def heavy_work_slot():
    """Reserve a slot for vision/upload work; release when the request finishes."""
    global _heavy_inflight
    raise_if_overloaded()
    async with _slot_lock:
        if _heavy_inflight >= _heavy_limit():
            raise HTTPException(status_code=503, detail=capacity_detail())
        _heavy_inflight += 1
    try:
        yield
    finally:
        async with _slot_lock:
            _heavy_inflight = max(0, _heavy_inflight - 1)