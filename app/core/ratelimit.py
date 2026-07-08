"""In-process sliding-window rate limits.

Single-container interim (same posture as capacity_service): buckets live in
module memory, keyed by scope+identity. When the app scales past one
container, swap the store for Redis without changing call sites.
"""
import threading
import time
from collections import deque

from fastapi import HTTPException, Request

_BUCKETS: dict[str, deque] = {}
_LOCK = threading.Lock()
_MAX_BUCKETS = 10_000


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _prune_locked(now: float) -> None:
    if len(_BUCKETS) <= _MAX_BUCKETS:
        return
    stale = [k for k, dq in _BUCKETS.items() if not dq or now - dq[-1] > 3600]
    for k in stale:
        _BUCKETS.pop(k, None)


def enforce(
    request: Request,
    *,
    scope: str,
    limit: int,
    window_seconds: int,
    identity: str | None = None,
) -> None:
    """Raise 429 when `identity` (default: client IP) exceeds limit/window."""
    ident = identity or client_ip(request)
    key = f"{scope}:{ident}"
    now = time.time()
    with _LOCK:
        _prune_locked(now)
        bucket = _BUCKETS.setdefault(key, deque())
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = max(1, int(window_seconds - (now - bucket[0])))
            raise HTTPException(
                429,
                detail={
                    "error": "rate_limited",
                    "message": (
                        "Too many requests — please wait a bit and try again."
                    ),
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)
