# MatchForge — Agent Rules

## Session start (required)

At the **beginning of every session**, before planning or coding:

```bash
/opt/matchforge/scripts/session_start.sh
```

Then read **`data/asana_state.json`** for the current punchlist, roadmap, and open decisions from Asana.

- **Asana project:** [MatchForge](https://app.asana.com/0/1215469600213575) in **My Workspace**
- **PAT:** local secrets file → `ASANA_PAT` (never commit; maintainer uses `~/.matchforge_secrets`)
- **Bootstrap (one-time):** `python scripts/asana_bootstrap.py --workspace "My Workspace"`
- **Config:** `scripts/asana_config.json` (project GID, no secrets)

Align session work with open Asana tasks. Mark tasks complete in Asana when shipping.

## App

- Root: `/opt/matchforge/`
- Dashboard: http://localhost/dashboard (nginx :80) or :8000
- Service: `systemctl status matchforge` (if installed via systemd)
- Secrets: `.env` locally (never commit); API keys outside the repo

## GitHub

- **Repo:** https://github.com/jfodchuk/MatchForge (public, MIT)
- **Profile:** https://github.com/jfodchuk
- **PAT:** `GITHUB_TOKEN` in local secrets file only (never commit)
- Push: `git push origin main` (use credential helper or `gh auth`, not token in remote URL)

## Engineering

Karpathy guidelines: surgical changes, simplicity first, verifiable success criteria.

## Responsible use

Privacy-first, local-by-default. Profile data is decision-support only — not ground truth about real people.