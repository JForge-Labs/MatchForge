"""In-process upload job registry.

Single-container interim (per scale plan): jobs live in module memory and die
with the process — exactly as durable as the in-process task doing the work.
The job-id + poll API is shaped so a Redis/DB-backed queue can slot in later
without changing the frontend.
"""
import secrets
import threading
import time

_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_MAX_JOBS = 300
_MAX_AGE_SECONDS = 6 * 3600

FILE_STAGES = ("queued", "analyzing", "scoring", "done", "failed")


def _prune_locked() -> None:
    now = time.time()
    stale = [
        job_id
        for job_id, job in _JOBS.items()
        if now - job["created_at"] > _MAX_AGE_SECONDS
    ]
    for job_id in stale:
        _JOBS.pop(job_id, None)
    while len(_JOBS) >= _MAX_JOBS:  # called pre-insert; stay ≤ cap after adding
        oldest = min(_JOBS, key=lambda j: _JOBS[j]["created_at"])
        _JOBS.pop(oldest, None)


def create_job(account_id: int, filenames: list[str]) -> dict:
    job = {
        "id": secrets.token_urlsafe(12),
        "account_id": account_id,
        "status": "queued",  # queued | running | done | error
        "created_at": time.time(),
        "files": [
            {"name": name, "stage": "queued", "profile_id": None,
             "merged": False, "error": None}
            for name in filenames
        ],
        "message": None,
        "balance": None,
        "error": None,
    }
    with _LOCK:
        _prune_locked()
        _JOBS[job["id"]] = job
    return job


def get_job(job_id: str, account_id: int) -> dict | None:
    job = _JOBS.get(job_id)
    if not job or job["account_id"] != account_id:
        return None
    return job


def set_file_stage(job: dict, index: int, stage: str, **fields) -> None:
    entry = job["files"][index]
    entry["stage"] = stage
    entry.update(fields)


def public_view(job: dict) -> dict:
    return {key: value for key, value in job.items() if key != "account_id"}
