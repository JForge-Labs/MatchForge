#!/usr/bin/env python3
"""Session wrap 2026-06-07 — mark shipped work, resolve decisions, refresh cache."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import httpx

API = "https://app.asana.com/api/1.0"
PROJECT_GID = "1215469600213575"
SESSION_DATE = "2026-06-07"

COMPLETE = {
    "1215471468272576": (
        "BILLING_ENABLED=true prod · dynamic Stripe top-up ($10 min) · "
        "webhook fix v0.2.6 · live payments · 100 signup grant v0.2.7 · "
        "referral 50 tokens on referred user first paid top-up"
    ),
    "1215469586724910": (
        "Resolved: private commercial repo · jfodchuk/MatchForge · "
        "internal README/CONTRIBUTING/PROJECT_INSTRUCTIONS"
    ),
    "1215472017483998": "/legal/privacy live · footer link · policy version 2026-06-08",
    "1215472307871335": "/legal/terms live · /legal/accept gate before onboarding",
    "1215472307881726": (
        "policies_accepted gate blocks onboarding/uploads until Terms+Privacy accepted; "
        "timestamp + version stored on UserProfile"
    ),
}

UPDATE_NOTES = {
    "1215469586701323": (
        "Admin operator dashboard shipped v0.2.8–v0.2.10 · /admin · ADMIN_EMAILS · "
        "metrics, accounts, ledger, token grants. Remaining: team workspaces."
    ),
    "1215469645329909": (
        "Onboarding simplified: single name + profile photo (nav avatar bubble). "
        "Trait/weight editor without DB access still open."
    ),
    "1215471468272639": (
        "Prod billing live · SIGNUP_GRANT_TOKENS=100 · SEED_MIN_TOKENS=0 · "
        "referral reward on first referred top-up (not onboarding)."
    ),
}

NEW_SHIPPED = [
    (
        "Stripe live billing + dynamic top-up (v0.2.5–v0.2.7)",
        "BILLING_ENABLED prod · Stripe Checkout dynamic amount · TOKENS_PER_USD=20 · "
        "webhook + success-page reconcile · referral on first paid top-up.",
    ),
    (
        "Share link 10-minute view window (v0.2.3)",
        "Branded share_expired.html · share_opens table · bot-aware first-human-open logic.",
    ),
    (
        "Admin operator dashboard (v0.2.8–v0.2.10)",
        "/admin for ADMIN_EMAILS · metrics · recent accounts · token ledger · grant API · "
        "DO spec ADMIN_EMAILS pushed.",
    ),
    (
        "Profile panel + account delete (v0.2.8)",
        "Nav avatar bubble · edit/billing links · POST /account/delete with DELETE confirm · "
        "single name + profile photo identity.",
    ),
    (
        "Private repo + operator docs (v0.2.8)",
        "GitHub private · README/CONTRIBUTING/PROJECT_INSTRUCTIONS · charter link removed from footer.",
    ),
]


def client() -> httpx.Client:
    pat = os.environ.get("ASANA_PAT", "").strip()
    if not pat:
        for line in Path("/root/.matchforge_secrets").read_text().splitlines():
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
    sections = c.get(f"/projects/{PROJECT_GID}/sections", params={"opt_fields": "name"}).json()["data"]
    return {s["name"]: s["gid"] for s in sections}


def complete_task(c: httpx.Client, gid: str, note: str) -> None:
    task = c.get(f"/tasks/{gid}", params={"opt_fields": "notes,name"}).json()["data"]
    prior = (task.get("notes") or "").strip()
    notes = f"{prior}\n\nShipped {SESSION_DATE} · {note}".strip()
    c.put(f"/tasks/{gid}", json={"data": {"completed": True, "notes": notes}}).raise_for_status()
    print(f"✓ completed: {task['name']}")


def update_notes(c: httpx.Client, gid: str, note: str) -> None:
    task = c.get(f"/tasks/{gid}", params={"opt_fields": "notes,name"}).json()["data"]
    prior = (task.get("notes") or "").strip()
    c.put(
        f"/tasks/{gid}",
        json={"data": {"notes": f"{prior}\n\nUpdated {SESSION_DATE} · {note}".strip()}},
    ).raise_for_status()
    print(f"↻ updated: {task['name']}")


def add_shipped(c: httpx.Client, section_gid: str, name: str, notes: str) -> None:
    task = c.post(
        "/tasks",
        json={
            "data": {
                "name": name,
                "notes": f"Shipped {SESSION_DATE} · {notes}",
                "completed": True,
                "projects": [PROJECT_GID],
            }
        },
    ).json()["data"]
    c.post(f"/sections/{section_gid}/addTask", json={"data": {"task": task["gid"]}}).raise_for_status()
    print(f"+ shipped: {name}")


def main() -> int:
    c = client()
    sections = section_map(c)
    shipped_gid = sections.get("✅ v0.1 — Shipped")
    if not shipped_gid:
        raise SystemExit(f"Missing shipped section: {list(sections)}")

    for gid, note in COMPLETE.items():
        complete_task(c, gid, note)

    for gid, note in UPDATE_NOTES.items():
        update_notes(c, gid, note)

    for name, notes in NEW_SHIPPED:
        add_shipped(c, shipped_gid, name, notes)

    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, str(root / "scripts" / "asana_sync.py")],
        check=True,
        env={**os.environ},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())