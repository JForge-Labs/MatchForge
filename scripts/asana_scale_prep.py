#!/usr/bin/env python3
"""Add scale-prep punchlist to Asana (foundational work — act on DO when needed)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

API = "https://app.asana.com/api/1.0"
PROJECT_GID = "1215469600213575"
SECTION_NAME = "🚀 Scale Prep"

# Existing tasks to cross-link
EXISTING_VISION_COMBINE_GID = "1215469600233338"
EXISTING_SPACES_GID = "1215471484847501"

SHIPPED = [
    (
        "At-capacity UX + in-process upload gates",
        """Shipped 2026-06-07 · v0.2.12+

FOUNDATION (live):
• /at-capacity page + thoughtful 503 JSON for API calls
• capacity_service.heavy_work_slot() on upload + onboarding
• OVERLOAD_MODE=true manual kill-switch on DO
• CAPACITY_MAX_CONCURRENT_UPLOADS (default 2)

RUNBOOK — flip when taxed:
1. Set OVERLOAD_MODE=true on prod DO app (pauses signups + heavy work gracefully)
2. Scale containers (see next task)
3. Drop SIGNUP_GRANT_TOKENS (see surge runbook task)

Blockers: none
Prerequisites: none""",
    ),
]

PUNCHLIST = [
    (
        "Surge runbook: DO horizontal scale (2–4 containers)",
        """Trigger: sustained 503s, upload queue backlog, or proactive before viral push.

ACTION:
• Update infrastructure/deploy/matchforge.app.yaml — migrate off basic-xs (no manual scale)
• Target: apps-s-1vcpu-2gb or professional-s, instance_count: 2–4
• Deploy via git tag → GHA deploy-prod

BLOCKER: basic-xs legacy slug cannot add containers — must change instance_size_slug first.

PREREQUISITES: CI/CD pipeline (✅ shipped)

NOTES: Each container = separate uvicorn; in-process semaphore is per-container until Redis queue ships.""",
    ),
    (
        "Surge runbook: drop SIGNUP_GRANT_TOKENS to 12–24 (1–2 analyses)",
        """Trigger: traffic spike + xAI cost concern; flip on DO without code deploy.

ACTION (prod env only):
• SIGNUP_GRANT_TOKENS=12 → 1 profile_screenshot analysis (12 tokens each)
• SIGNUP_GRANT_TOKENS=24 → 2 analyses
• Current default: 100 (≈8 analyses)

BLOCKER: none — env var already wired (credit_service.grant_signup_credits)

PREREQUISITES: BILLING_ENABLED=true (✅ prod live)

Revert to 100 when capacity normalizes.""",
    ),
    (
        "Upload job queue (fast accept → async Grok pipeline)",
        """Accept screenshot immediately; return job ID; poll or SSE for result.

BLOCKER: Redis not in prod app spec — need DO Managed Redis, Upstash, or Valkey.

PREREQUISITES:
• At-capacity UX (✅ shipped)
• DO scale-out runbook (for worker containers)

DEPENDS ON: Redis before multi-container upload fairness""",
    ),
    (
        "Rate limiting (signup, auth, upload)",
        """Per-IP + per-email limits on /signup, /auth/*, /toolbox/upload-screenshots.

BLOCKER: In-memory limits only work on single container; multi-instance needs Redis.

PREREQUISITES: Redis (upload job queue task)

SUGGESTED: 10 signups/IP/hr, 30 uploads/account/hr during surge""",
    ),
    (
        "Async SMTP email queue",
        """Decouple signup/login from blocking smtplib round-trip (30s timeout today).

BLOCKER: needs job queue infrastructure

PREREQUISITES: Redis + worker (upload queue task)

Prevents signup latency cascade during bursts.""",
    ),
    (
        "xAI rate-limit retry + backpressure",
        """Retry 429/503 from Grok with exponential backoff; surface capacity UX not raw errors.

PREREQUISITES: capacity_service (✅ shipped)

FULL FIX depends on: upload job queue (decouple user wait from API limits)""",
    ),
    (
        "PgBouncer / DB pool tuning for multi-container",
        """SQLAlchemy default pool (5+10) × N containers can exhaust managed PG connections.

ACTION: pool_size/max_overflow env config; consider PgBouncer when instance_count > 2.

BLOCKER: only matters after horizontal scale

PREREQUISITES: DO scale-out runbook""",
    ),
    (
        "Signup captcha / bot protection",
        """Cloudflare Turnstile or hCaptcha on /signup before grant farming at scale.

BLOCKER: none

PREREQUISITES: recommended before viral social push; not required for soft launch""",
    ),
    (
        "Load test playbook (1K signups / 24h simulation)",
        """Document k6/locust scripts: landing, signup, verify stub, onboarding, 2-upload session.

PREREQUISITES: queue + scale runbooks drafted

Use staging (dev.match-forge.com) — never load-test prod xAI key unchecked.""",
    ),
]

UPDATE_EXISTING = {
    EXISTING_VISION_COMBINE_GID: (
        "SCALE PRIORITY — combine 6 Grok calls/upload → 2–3 before major traffic. "
        "Cost + latency leverage; no infra blocker. Links: 🚀 Scale Prep section."
    ),
    EXISTING_SPACES_GID: (
        "SCALE BLOCKER for multi-container — ephemeral DO disk loses uploads on redeploy. "
        "Required before scaling past 1 web container. Links: 🚀 Scale Prep section."
    ),
}


def client() -> httpx.Client:
    pat = os.environ.get("ASANA_PAT", "").strip()
    if not pat:
        secrets = Path("/root/.matchforge_secrets").read_text()
        for line in secrets.splitlines():
            if line.startswith("ASANA_PAT="):
                pat = line.split("=", 1)[1].strip()
                break
    if not pat:
        raise SystemExit("ASANA_PAT not set")
    return httpx.Client(
        base_url=API,
        headers={"Authorization": f"Bearer {pat}", "Accept": "application/json"},
        timeout=60.0,
    )


def section_map(c: httpx.Client) -> dict[str, str]:
    sections = c.get(
        f"/projects/{PROJECT_GID}/sections", params={"opt_fields": "name"}
    ).json()["data"]
    return {s["name"]: s["gid"] for s in sections}


def ensure_section(c: httpx.Client, name: str) -> str:
    sections = section_map(c)
    if name in sections:
        return sections[name]
    created = c.post(
        f"/projects/{PROJECT_GID}/sections",
        json={"data": {"name": name}},
    ).json()["data"]
    print(f"+ section: {name}")
    return created["gid"]


def add_task(
    c: httpx.Client, section_gid: str, name: str, notes: str, *, done: bool = False
) -> None:
    task = c.post(
        "/tasks",
        json={
            "data": {
                "name": name,
                "notes": notes,
                "completed": done,
                "projects": [PROJECT_GID],
            }
        },
    ).json()["data"]
    c.post(
        f"/sections/{section_gid}/addTask",
        json={"data": {"task": task["gid"]}},
    ).raise_for_status()
    print(f"+ {'shipped' if done else 'open'}: {name}")


def update_notes(c: httpx.Client, gid: str, note: str) -> None:
    task = c.get(f"/tasks/{gid}", params={"opt_fields": "notes,name"}).json()["data"]
    prior = (task.get("notes") or "").strip()
    c.put(
        f"/tasks/{gid}",
        json={
            "data": {
                "notes": f"{prior}\n\nUpdated 2026-06-07 · {note}".strip(),
            }
        },
    ).raise_for_status()
    print(f"↻ linked: {task['name']}")


def main() -> int:
    c = client()
    section_gid = ensure_section(c, SECTION_NAME)

    for name, notes in SHIPPED:
        add_task(c, section_gid, name, notes, done=True)

    for name, notes in PUNCHLIST:
        add_task(c, section_gid, name, notes, done=False)

    for gid, note in UPDATE_EXISTING.items():
        update_notes(c, gid, note)

    print("Done — run scripts/asana_sync.py to refresh cache")
    return 0


if __name__ == "__main__":
    sys.exit(main())