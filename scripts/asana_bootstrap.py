#!/usr/bin/env python3
"""Bootstrap MatchForge project in Asana: charter, punchlist, roadmap.

Usage:
    export ASANA_PAT="your_personal_access_token"
    python scripts/asana_bootstrap.py
    python scripts/asana_bootstrap.py --workspace "My Workspace"
    python scripts/asana_bootstrap.py --dry-run

Get a PAT: Asana → Settings → Apps → Developer Console → Personal access token
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

API = "https://app.asana.com/api/1.0"
PROJECT_NAME = "MatchForge"
DEFAULT_WORKSPACE = "My Workspace"
PROJECT_GID = "1215469600213575"  # canonical project in My Workspace

CHARTER = """MatchForge — Project Charter (v0.1 R&D)

VISION
Self-hosted, local-first AI dating intelligence toolbox. Users drag screenshots or
enter usernames. The system establishes a user profile (gender + intentions), builds
a personalized preference vector, ranks/percolates matches, enriches with public
social data, and scores authenticity (catfish, filters, bots) — all on-box.

CORE PHILOSOPHY
• Screenshot-first — universal input, no platform API drama
• Privacy-first — Ollama local by default; cloud optional
• Toolbox model — drag-and-drop for real users
• Trust layer — authenticity scoring before percolation
• Iterative R&D — narrow MVP now; expand later

RESPONSIBLE USE
Profile data describes real people who have not consented to external ranking.
Local-only storage; decision-support not ground truth. Respect platform ToS.

TECH STACK
FastAPI · PostgreSQL+pgvector · Redis · Ollama (vision+LLM) · Playwright

DEV ENV
Self-hosted LXC/container · http://localhost/dashboard
"""

SECTIONS: dict[str, list[dict]] = {
    "✅ v0.1 — Shipped": [
        {"name": "FastAPI skeleton + systemd + nginx + firewall", "done": True},
        {"name": "PostgreSQL + pgvector + Redis + Ollama", "done": True},
        {"name": "Screenshot upload → vision extraction pipeline", "done": True},
        {"name": "User onboarding (gender + intentions + preference vector)", "done": True},
        {"name": "Personalized ranking + percolation dashboard", "done": True},
        {"name": "Trust layer (authenticity, filters, catfish, bot scores)", "done": True},
        {"name": "Public social enrichment (Playwright)", "done": True},
        {"name": "Feedback loop (like/pass/top)", "done": True},
        {"name": "README + test samples", "done": True},
    ],
    "🔨 Active Punchlist": [
        {"name": "Bump dev host to 12GB RAM / 6 CPU", "notes": "Required for llava vision; moondream is dev fallback"},
        {"name": "Re-auth Tailscale on dev host", "notes": "Remote access via tailnet"},
        {"name": "Speed up trust pipeline (combine vision calls)", "notes": "2 vision + 2 LLM calls per upload is too slow on CPU"},
        {"name": "Preference vector settings UI", "notes": "Edit traits/weights without DB access"},
        {"name": "Export ranked shortlist (JSON/CSV)", "notes": "Conversation starters + trust breakdown"},
        {"name": "Wire nomic-embed-text for vector similarity ranking"},
        {"name": "APScheduler background enrichment jobs"},
        {"name": "React/Tailwind frontend evaluation", "notes": "vs staying on FastAPI templates"},
    ],
    "🗺️ Roadmap — v0.2": [
        {"name": "Multi-screenshot profiles (multiple photos per match)", "due": "2026-07"},
        {"name": "Embedding-based similarity + preference learning from feedback"},
        {"name": "Username lookup flow (non-screenshot input)"},
        {"name": "Improved social enrichment (rate limits, caching)"},
        {"name": "Conversation starter export + match notes"},
        {"name": "Basic API auth (single-user API key)"},
    ],
    "🗺️ Roadmap — v0.3+": [
        {"name": "Playwright platform connectors (authorized data only)"},
        {"name": "Multi-user auth + per-user preference vectors"},
        {"name": "Mobile-friendly PWA dashboard"},
        {"name": "Optional cloud LLM fallback (OpenAI/Anthropic)"},
        {"name": "Docker Compose production stack"},
        {"name": "v1.0 packaging + install script"},
    ],
    "🤔 Open Decisions": [
        {
            "name": "DECISION: Public vs private GitHub repo?",
            "notes": """OPTIONS:

PUBLIC REPO (recommended for toolbox/OSS angle)
+ Community contributors, issues, stars, credibility
+ Easier CI, forks, documentation visibility
+ Aligns with self-hosted / privacy-first marketing
− Responsible-use boundary must be very clear in README/LICENSE
− No secrets in repo ever (.env.example only)
− Consider AGPL or MIT + ethics disclaimer

PRIVATE REPO
+ Full control, no accidental exposure of R&D direction
+ Simpler while iterating fast
− Harder to share, no community trust signals
− Manual backup/collab only

RECOMMENDATION: Public repo with private dev secrets (.env, PATs) on CT only.
Ship with strong README responsible-use section + SECURITY.md. Defer connectors
that touch platform ToS until legal review.""",
        },
        {
            "name": "DECISION: Frontend — HTMX/templates vs React/Tailwind?",
            "notes": "Templates work now. React if we need rich interactivity + component reuse.",
        },
        {
            "name": "DECISION: Distribution model — self-hosted only vs hosted SaaS?",
            "notes": "Charter says self-hosted. Revisit if monetization needed.",
        },
    ],
}


class AsanaClient:
    def __init__(self, pat: str, dry_run: bool = False):
        self.dry_run = dry_run
        self.client = httpx.Client(
            base_url=API,
            headers={"Authorization": f"Bearer {pat}", "Accept": "application/json"},
            timeout=30.0,
        )

    def _req(self, method: str, path: str, **kwargs) -> dict:
        if self.dry_run:
            print(f"[DRY RUN] {method} {path}")
            return {"data": {}}
        resp = self.client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            raise RuntimeError(f"Asana {method} {path} → {resp.status_code}: {resp.text}")
        return resp.json()

    def workspaces(self) -> list[dict]:
        return self._req("GET", "/workspaces")["data"]

    def find_project(self, workspace_gid: str, name: str) -> dict | None:
        data = self._req(
            "GET",
            "/projects",
            params={"workspace": workspace_gid, "opt_fields": "name,gid"},
        )["data"]
        return next((p for p in data if p["name"] == name), None)

    def create_project(self, workspace_gid: str, team_gid: str | None) -> dict:
        body: dict = {
            "data": {
                "name": PROJECT_NAME,
                "notes": CHARTER,
                "workspace": workspace_gid,
                "public": False,
            }
        }
        if team_gid:
            body["data"]["team"] = team_gid
        return self._req("POST", "/projects", json=body)["data"]

    def create_section(self, project_gid: str, name: str) -> dict:
        return self._req(
            "POST",
            f"/projects/{project_gid}/sections",
            json={"data": {"name": name}},
        )["data"]

    def create_task(
        self,
        name: str,
        project_gid: str,
        section_gid: str,
        notes: str = "",
        completed: bool = False,
    ) -> dict:
        return self._req(
            "POST",
            "/tasks",
            json={
                "data": {
                    "name": name,
                    "notes": notes,
                    "completed": completed,
                    "projects": [project_gid],
                    "memberships": [{"project": project_gid, "section": section_gid}],
                }
            },
        )["data"]


def pick_workspace(workspaces: list[dict], hint: str | None) -> dict:
    if hint:
        match = next(
            (w for w in workspaces if hint.lower() in w["name"].lower()),
            None,
        )
        if not match:
            raise SystemExit(f"Workspace matching '{hint}' not found.")
        return match
    if len(workspaces) == 1:
        return workspaces[0]
    print("Available workspaces:")
    for w in workspaces:
        print(f"  - {w['name']} ({w['gid']})")
    raise SystemExit("Multiple workspaces — pass --workspace \"Name\"")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap MatchForge in Asana")
    parser.add_argument("--workspace", help="Workspace name substring")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    pat = os.environ.get("ASANA_PAT", "").strip()
    if not pat and not args.dry_run:
        raise SystemExit(
            "Set ASANA_PAT environment variable.\n"
            "Asana → Settings → Apps → Developer Console → Personal access token"
        )

    client = AsanaClient(pat or "dry-run", dry_run=args.dry_run)

    workspaces = client.workspaces()
    ws = pick_workspace(workspaces, args.workspace)
    print(f"Using workspace: {ws['name']} ({ws['gid']})")

    existing = client.find_project(ws["gid"], PROJECT_NAME)
    if existing:
        print(f"Project already exists: {PROJECT_NAME} ({existing['gid']})")
        print(f"Open: https://app.asana.com/0/{existing['gid']}")
        if not args.dry_run:
            raise SystemExit("Delete or rename existing project to re-bootstrap.")
        project = existing
    else:
        project = client.create_project(ws["gid"], team_gid=None)
        print(f"Created project: {project.get('gid', 'dry-run')}")

    project_gid = project.get("gid", "dry-run")
    section_gids: dict[str, str] = {}

    for section_name in SECTIONS:
        sec = client.create_section(project_gid, section_name)
        section_gids[section_name] = sec.get("gid", section_name)
        print(f"  Section: {section_name}")

    task_count = 0
    for section_name, tasks in SECTIONS.items():
        for t in tasks:
            client.create_task(
                name=t["name"],
                project_gid=project_gid,
                section_gid=section_gids[section_name],
                notes=t.get("notes", ""),
                completed=t.get("done", False),
            )
            task_count += 1

    print(f"\nDone — {task_count} tasks across {len(SECTIONS)} sections.")
    if project_gid != "dry-run":
        print(f"Open: https://app.asana.com/0/{project_gid}")


if __name__ == "__main__":
    main()