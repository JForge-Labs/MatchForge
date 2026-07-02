# MatchForge — Project Instructions

**Purpose:** Operating instructions for AI agents and contributors working on MatchForge. Read this + `data/asana_state.json` (after `scripts/asana_sync.py`) at session start.

> Operator-specific details (internal hosts, deploy app IDs, secrets locations) live in the maintainer's private ops doc — not in this repository.

---

## What MatchForge Is

**Personal safety and basic due diligence tool** for dating. Users upload **publicly visible profile screenshots** or submit an **X handle**; AI (xAI Grok + the official X API) scores authenticity, compatibility, social proof, and safety signals into a **private shortlist**. Not a dating app, background check, or ground truth about anyone.

**Legal gate:** Users must accept Terms + Privacy at `/legal/accept` before onboarding or uploads. Policy version in `app/utils/legal.py` → `POLICIES_VERSION`.

---

## Environments

| Tier | URL | Deploy |
|------|-----|--------|
| **Dev** | local (`uvicorn app.main:app --reload`) | — |
| **Stage** | https://dev.match-forge.com | `git push origin main` |
| **Prod** | https://match-forge.com | `git tag vX.Y.Z && git push origin vX.Y.Z` |

`APP_ENV`: `development` · `staging` · `production`

**Iterate on dev first.** Push `main` for stage; tag for prod. Do not deploy prod on every `main` push.

---

## Session Start Checklist

```bash
scripts/session_start.sh   # if present
source venv/bin/activate
python scripts/asana_sync.py   # refresh data/asana_state.json (needs ASANA_PAT)
```

Read: `AGENTS.md`, `data/asana_state.json`, `infrastructure/deploy/RUNBOOK.md` for deploy tasks.

---

## Engineering Rules

1. **Surgical changes** — only modify what the task requires; match existing style.
2. **Execute, don't instruct** — run commands yourself; verify with health checks and tests.
3. **Secrets** — never commit `.env` or tokens; local secrets files are chmod 600 and gitignored.
4. **DB** — dev database only for local work; confirm before destructive ops. Migrations follow the `ALTER TABLE IF NOT EXISTS` pattern (`scripts/migrate_*.py`).
5. **Responsible use** — build only against public data or data the user is authorized to access; scores are private decision-support; respect platform ToS (official X API + Grok tools only — no scraping X).
6. **Legal** — do not bypass `/legal/accept` gate; keep public-source-only framing in copy; append AI disclaimers on trust/ranking outputs (`app/utils/legal.py`).

---

## Stack Quick Reference

- **Backend:** FastAPI, SQLAlchemy, PostgreSQL 16 + pgvector, Redis
- **AI:** xAI Grok — vision, fast/reasoning text, and server-side agentic tools (`x_search`, `web_search`)
- **X data:** official X API v2 (`x_api_service.py`), TTL-cached
- **Frontend:** Jinja2 templates + `static/app.js`, `static/onboarding.js`, `static/style.css`
- **Auth:** Email magic link + sessions; per-account `UserProfile`
- **Billing:** Token ledger; Stripe top-ups when `BILLING_ENABLED=true`
- **Admin:** `/admin` for operators in `ADMIN_EMAILS`

### Key paths

```
app/api/          auth, legal, onboarding, toolbox, profiles, x_verify, dashboard
app/services/     llm (Grok + agentic), x_api, x_verify, threat_intel, vision,
                  trust, ranking, onboarding, share, agent, legal
app/models/       Profile, Ranking, UserProfile, Account, PreferenceVector, XProfileCache
docs/             ARCHITECTURE, X_API_USAGE, GROK_AGENTS, PRIVACY, demo/
templates/        dashboard.html, verify_share.html, onboarding.html, legal/, share.html
infrastructure/deploy/   app specs, RUNBOOK.md
```

### Common commands

```bash
curl -s http://127.0.0.1:8000/health
./venv/bin/python scripts/init_db.py
./venv/bin/python scripts/migrate_v2_x.py
./venv/bin/python tests/test_x_verify.py
```

---

## UX & Product Conventions

- **Profile cards:** Compatibility / Attractiveness / Red flags as top score bars; trust badges include 𝕏 Social Proof when verified.
- **X verification:** Per-tile handle input + consent line; agent trace and citations render in the report; badge share is opt-in.
- **Agent panel:** Paste, drag-drop, and attach images; themed button.
- **Share:** No real names in OG/messenger previews; rotating hooks; referral link in share text. Verification badges show handle + verdict + score only.
- **Delete:** Instant profile delete on card; account delete via profile panel.
- **Env banner:** Shown on dev/staging; hidden on production.

---

## Do NOT

- Rank or expose real people publicly without consent framing
- Remove or weaken legal/policy acceptance gates without explicit user request
- Push secrets, PATs, or API keys to git
- Scrape X — use the official API and Grok tools only
- Deploy to prod without a version tag
- Grandfather users past policy version bumps — bump `POLICIES_VERSION` when legal text changes

---

## When Task Is Complete

1. Restart the service if code/templates changed
2. Hit `/health` and spot-check affected UI routes
3. Run relevant tests in `tests/`
4. Commit with clear message; push `main` and/or tag per user instruction
5. Update Asana punchlist
6. Report: what changed, how to verify, deploy status, open issues

---

## Escalate / Ask User When

- Destructive DB operations on production
- Legal copy changes that need counsel review
- Billing/Stripe changes
- New third-party data sources or platform connectors (ToS risk)
- Policy version bump affecting all users

---

*Last updated: 2026-07-02 · v2 X-verification overhaul*
