#!/usr/bin/env python3
"""One-shot Asana maintenance: complete shipped/obsolete tasks, add new items."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

API = "https://app.asana.com/api/1.0"
PROJECT_GID = "1215469600213575"

COMPLETE = {
    # Obsolete CI/CD blockers — shipped 2026-06-07
    "1215484196272385": "Shipped · .github/workflows/deploy.yml · main→stage, tag→prod",
    "1215471272632261": "Shipped · matchforge-dev on DO · dev.match-forge.com · a41e0b2e",
    "1215471339895508": "Shipped · PAT with workflow scope · CI deploy live",
}

UPDATE_NOTES = {
    "1215469645329909": (
        "Partial — /onboarding covers goals + optional identity (handle, selfie, bio). "
        "Trait/weight editor without DB access still open."
    ),
    "1215469597511366": (
        "Deferred — prod/stage use Grok/xAI cloud vision. Local Ollama optional on CT108 only. "
        "Reopen if we return to on-box llava."
    ),
    "1215469600233338": (
        "Still relevant but lower priority with Grok API path. Combine vision calls when optimizing cost/latency."
    ),
    "1215469425854122": (
        "Partial — site.webmanifest, PNG icons, apple-touch-icon, OG card shipped v0.2.1. "
        "Offline/service-worker still open."
    ),
    "1215469586701323": (
        "Shipped — multi-user email auth + per-account preference vectors. "
        "Remaining: admin roles, team workspaces."
    ),
}

NEW_SHIPPED = [
    (
        "CI/CD dev→stage→prod pipeline",
        "main push → dev.match-forge.com; v* tag → match-forge.com. Commits ae1052d, 6e9556a.",
    ),
    (
        "Premium dashboard UX (v0.2)",
        "Score bars, profile delete, unified agent prompt, optional user fields, env banner, favicon.",
    ),
    (
        "Share previews + PWA icons (v0.2.1)",
        "OG card, privacy-safe share hooks, homescreen PNG icons, referral link previews.",
    ),
    (
        "Profile dedup + merge on upload",
        "platform+username merge; scripts/dedupe_profiles.py for legacy dupes.",
    ),
]

NEW_PUNCHLIST = [
    (
        "Privacy Policy page (hosted SaaS)",
        "Publish /privacy covering data collected (screenshots, emails, selfies), Grok/xAI processing, retention, deletion rights. Link from footer + signup.",
    ),
    (
        "Terms of Service + signup acknowledgement",
        "Publish /terms; checkbox on signup/onboarding: responsible use, no non-consensual ranking, platform ToS compliance, decision-support disclaimer.",
    ),
    (
        "First-upload consent gate",
        "Before first screenshot upload: explicit ack that user has right to analyze profiles shown and data stays in their account; block upload until accepted; store consent timestamp.",
    ),
]


def client() -> httpx.Client:
    pat = os.environ.get("ASANA_PAT", "").strip()
    if not pat:
        pat = Path("/root/.matchforge_secrets").read_text()
        for line in pat.splitlines():
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


def complete_task(c: httpx.Client, gid: str, note: str | None = None) -> None:
    payload: dict = {"completed": True}
    if note:
        task = c.get(f"/tasks/{gid}", params={"opt_fields": "notes"}).json()["data"]
        prior = (task.get("notes") or "").strip()
        payload["notes"] = f"{prior}\n\nShipped 2026-06-07 · {note}".strip()
    c.put(f"/tasks/{gid}", json={"data": payload}).raise_for_status()
    print(f"✓ completed {gid}")


def update_notes(c: httpx.Client, gid: str, note: str) -> None:
    task = c.get(f"/tasks/{gid}", params={"opt_fields": "notes,name"}).json()["data"]
    prior = (task.get("notes") or "").strip()
    c.put(
        f"/tasks/{gid}",
        json={"data": {"notes": f"{prior}\n\nUpdated 2026-06-07 · {note}".strip()}},
    ).raise_for_status()
    print(f"↻ updated {task['name']}")


def add_task_to_section(c: httpx.Client, section_gid: str, name: str, notes: str, done: bool = False) -> None:
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
    c.post(f"/sections/{section_gid}/addTask", json={"data": {"task": task["gid"]}}).raise_for_status()
    state = "shipped" if done else "added"
    print(f"+ {state}: {name}")


def main() -> int:
    c = client()
    sections = section_map(c)
    shipped_gid = sections.get("✅ v0.1 — Shipped")
    punch_gid = sections.get("🔨 Active Punchlist")
    if not shipped_gid or not punch_gid:
        raise SystemExit(f"Missing sections: {list(sections)}")

    for gid, note in COMPLETE.items():
        complete_task(c, gid, note)

    for gid, note in UPDATE_NOTES.items():
        update_notes(c, gid, note)

    for name, notes in NEW_SHIPPED:
        add_task_to_section(c, shipped_gid, name, f"Shipped 2026-06-07 · {notes}", done=True)

    for name, notes in NEW_PUNCHLIST:
        add_task_to_section(c, punch_gid, name, notes, done=False)

    print("Done — run scripts/asana_sync.py to refresh cache")
    return 0


if __name__ == "__main__":
    sys.exit(main())