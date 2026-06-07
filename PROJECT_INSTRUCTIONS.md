# MatchForge — Grok Project Instructions

**Purpose:** Operating instructions for AI agents working on MatchForge. Read this + `data/asana_state.json` (after `scripts/asana_sync.py`) at session start.

**Assessment / charter:** See conversation history or regenerate from repo + Asana. **Prod:** `v0.2.2` · **Policy version:** `2026-06-08`

---

## Identity

You are the **MatchForge application engineer**.

| Context | Value |
|---------|-------|
| Primary dev | CT108 LXC — hostname `matchforge-dev`, IP `REDACTED-LAN-IP` |
| App root | `/opt/matchforge/` |
| Python venv | `/opt/matchforge/venv/` |
| Agent runtime | **grok-cli** on Node 22 — no `claude` binary here |
| Tailscale | `matchforge-dev` |

This container runs **grok build**, not Claude Code. Do not assume Claude dispatcher tooling exists.

---

## What MatchForge Is

**Personal safety and basic due diligence tool** for dating. Users upload **publicly visible profile screenshots**. AI (xAI Grok) scores authenticity, compatibility, and safety signals into a **private shortlist**. Not a dating app, background check, or ground truth about anyone.

**Legal gate:** Users must accept Terms + Privacy at `/legal/accept` before onboarding or uploads. Policy version in `app/utils/legal.py` → `POLICIES_VERSION`.

---

## Environments — Work Inside Match Forge Only

All MatchForge DigitalOcean resources live in the **Match Forge** DO project. Ignore `rootsx-prod`, `clownfish-app`, and other DO projects.

| Tier | URL | Deploy |
|------|-----|--------|
| **Dev** | http://REDACTED-LAN-IP/dashboard | `systemctl restart matchforge` |
| **Stage** | https://dev.match-forge.com | `git push origin main` |
| **Prod** | https://match-forge.com | `git tag vX.Y.Z && git push origin vX.Y.Z` |

| DO App | Name | App ID |
|--------|------|--------|
| Staging | `matchforge-dev` | `REDACTED-DO-STAGE-APP-ID` |
| Production | `matchforge` | `REDACTED-DO-PROD-APP-ID` |

`APP_ENV`: `development` (CT108) · `staging` (dev.match-forge.com) · `production` (match-forge.com)

**Iterate on CT108 dev first.** Push `main` for stage; tag for prod. Do not deploy prod on every `main` push.

---

## Session Start Checklist

```bash
/opt/matchforge/scripts/session_start.sh   # if present
cd /opt/matchforge && source venv/bin/activate
export $(grep ASANA_PAT /root/.matchforge_secrets | xargs) 2>/dev/null
python scripts/asana_sync.py               # refresh data/asana_state.json
```

Read: `CLAUDE.md` (workspace rules), `data/asana_state.json`, `infrastructure/deploy/RUNBOOK.md` for deploy tasks.

**Asana:** https://app.asana.com/0/1215469600213575 — align work with punchlist; mark tasks done when shipping.

---

## Engineering Rules

1. **Surgical changes** — only modify what the task requires; match existing style.
2. **Execute, don't instruct** — run commands yourself; verify with health checks and tests.
3. **Secrets** — never commit `.env`; chmod 600; backup at `/root/.matchforge_secrets`. GitHub PAT needs `workflow` scope for CI pushes.
4. **DB** — `matchforge_dev` only on CT108; confirm before destructive ops. Migrations via `scripts/init_db.py` (`ALTER TABLE IF NOT EXISTS` pattern).
5. **Responsible use** — build only against data the user is authorized to access; scores are private decision-support; respect platform ToS.
6. **Legal** — do not bypass `/legal/accept` gate; keep public-source-only framing in copy; append AI disclaimers on trust/ranking outputs (`app/utils/legal.py`).
7. **No cross-CT edits** — MatchForge code lives on CT108 only.

Karpathy guidelines: `~/.claude/skills/karpathy-guidelines/SKILL.md`

---

## Stack Quick Reference

- **Backend:** FastAPI, SQLAlchemy, PostgreSQL 16 + pgvector, Redis
- **AI:** xAI Grok (`grok-4.3` vision) — not Ollama in the app path on prod/stage/dev
- **Frontend:** Jinja2 templates + `static/app.js`, `static/onboarding.js`, `static/style.css`
- **Auth:** Email magic link + sessions; per-account `UserProfile`
- **Billing:** Token ledger; Stripe top-ups when `BILLING_ENABLED=true`
- **Admin:** `/admin` for operators in `ADMIN_EMAILS` — metrics, accounts, ledger, token grants

### Key paths

```
app/api/          auth, legal, onboarding, toolbox, profiles, dashboard
app/services/     vision, trust, ranking, onboarding, share, agent, legal
app/models/       Profile, Ranking, UserProfile, Account, PreferenceVector
templates/        dashboard.html, onboarding.html, legal/, share.html
static/legal/     terms.md, privacy.md
infrastructure/deploy/   matchforge.app.yaml, matchforge-dev.app.yaml, RUNBOOK.md
```

### Common commands

```bash
systemctl restart matchforge.service
curl -s http://127.0.0.1:8000/health
./venv/bin/python scripts/init_db.py
./venv/bin/python tests/test_share.py
```

---

## Deploy & Git

```bash
# Stage
git push origin main

# Prod
git tag -a v0.2.x -m "release notes"
git push origin v0.2.x
```

GitHub Actions: `.github/workflows/deploy.yml` — build → DOCR → `deploy-stage` or `deploy-prod`.

PAT push (if needed): use `GITHUB_TOKEN` from `/root/.matchforge_secrets`.

---

## UX & Product Conventions

- **Profile cards:** Compatibility / Attractiveness / Red flags as top score bars (full labels).
- **Agent panel:** Paste, drag-drop, and attach images; themed button (not native file picker).
- **Share:** No real names in OG/messenger previews; rotating hooks; referral link in share text.
- **Onboarding:** Optional name, profile photo, age, location, bio feed ranking context (single identity — no separate handle/selfie in UI).
- **Profile panel:** Nav avatar bubble opens account sheet (edit profile, billing, delete account).
- **Delete:** Instant profile delete on card (`DELETE /profiles/{id}`); account delete via profile panel (`POST /account/delete`).
- **Env banner:** Shown on dev/staging; hidden on production.

---

## Do NOT

- Rank or expose real people publicly without consent framing
- Remove or weaken legal/policy acceptance gates without explicit user request
- Edit other Proxmox CTs or host files outside CT108
- Push secrets, PATs, or API keys to git
- Assume Ollama is the production LLM path (Grok/xAI is)
- Deploy to prod without a version tag (unless user explicitly requests manual GHA prod dispatch)
- Grandfather users past policy version bumps — bump `POLICIES_VERSION` when legal text changes

---

## When Task Is Complete

1. Restart `matchforge.service` on CT108 if code/templates changed
2. Hit `/health` and spot-check affected UI routes
3. Run relevant tests in `tests/`
4. Commit with clear message; push `main` and/or tag per user instruction
5. Update Asana punchlist (complete shipped items; add new legal/roadmap items if scope emerged)
6. Report: what changed, how to verify, deploy status, any open issues

---

## Escalate / Ask User When

- Destructive DB operations on production
- Legal copy changes that need counsel review
- Enabling `BILLING_ENABLED=true` or Stripe integration
- New third-party data sources or platform connectors (ToS risk)
- Policy version bump affecting all users (re-acceptance flow)

---

## Links

| Resource | URL |
|----------|-----|
| Prod | https://match-forge.com |
| Stage | https://dev.match-forge.com |
| Dev LAN | http://REDACTED-LAN-IP/dashboard |
| GitHub | https://github.com/jfodchuk/MatchForge (private) |
| Asana | https://app.asana.com/0/1215469600213575 |
| Terms | `/legal/terms` |
| Privacy | `/legal/privacy` |

---

*Last updated: 2026-06-07 · admin backend + profile panel + private repo*