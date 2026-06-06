#!/usr/bin/env python3
"""Pull MatchForge Asana project state into local cache for session context.

Run at the start of every dev session:
    cd /opt/matchforge && source venv/bin/activate
    export $(grep ASANA_PAT ~/.matchforge_secrets | xargs)
    python scripts/asana_sync.py

Writes: data/asana_state.json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

API = "https://app.asana.com/api/1.0"
PROJECT_GID = "1215469600213575"
PROJECT_URL = f"https://app.asana.com/0/{PROJECT_GID}"
WORKSPACE = "My Workspace"
OUT = Path(__file__).resolve().parents[1] / "data" / "asana_state.json"


def main() -> int:
    pat = os.environ.get("ASANA_PAT", "").strip()
    if not pat:
        print("ASANA_PAT not set — skip sync or: export $(grep ASANA_PAT ~/.matchforge_secrets | xargs)")
        return 1

    headers = {"Authorization": f"Bearer {pat}", "Accept": "application/json"}
    client = httpx.Client(base_url=API, headers=headers, timeout=60.0)

    proj = client.get(f"/projects/{PROJECT_GID}", params={"opt_fields": "name,notes"}).json()["data"]
    sections = client.get(
        f"/projects/{PROJECT_GID}/sections",
        params={"opt_fields": "name"},
    ).json()["data"]

    tasks_by_section: dict[str, list[dict]] = {}
    for sec in sections:
        tasks = client.get(
            f"/sections/{sec['gid']}/tasks",
            params={"opt_fields": "name,completed,notes,due_on,assignee.name"},
        ).json()["data"]
        tasks_by_section[sec["name"]] = [
            {
                "gid": t["gid"],
                "name": t["name"],
                "completed": t.get("completed", False),
                "due_on": t.get("due_on"),
                "assignee": (t.get("assignee") or {}).get("name"),
                "notes_preview": (t.get("notes") or "")[:300],
            }
            for t in tasks
        ]

    open_tasks = [
        t for tasks in tasks_by_section.values() for t in tasks if not t["completed"]
    ]
    done_tasks = [
        t for tasks in tasks_by_section.values() for t in tasks if t["completed"]
    ]

    state = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "project_gid": PROJECT_GID,
        "project_url": PROJECT_URL,
        "workspace": WORKSPACE,
        "project_name": proj["name"],
        "charter_notes": proj.get("notes", ""),
        "sections": tasks_by_section,
        "summary": {
            "open_count": len(open_tasks),
            "done_count": len(done_tasks),
            "open_tasks": [t["name"] for t in open_tasks],
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(state, indent=2))
    print(f"Synced {len(open_tasks)} open / {len(done_tasks)} done tasks")
    print(f"Project: {PROJECT_URL}")
    print(f"Cache: {OUT}")
    print("\n--- Active punchlist (open) ---")
    for sec, tasks in tasks_by_section.items():
        open_in_sec = [t for t in tasks if not t["completed"]]
        if open_in_sec and "Punchlist" in sec or "Decision" in sec or "Roadmap" in sec:
            print(f"\n{sec}:")
            for t in open_in_sec:
                print(f"  • {t['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())