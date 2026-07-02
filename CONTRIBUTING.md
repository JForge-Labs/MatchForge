# Contributing to MatchForge

Thanks for your interest! MatchForge is open source (MIT). Please read the
responsible-use notes in [`docs/PRIVACY.md`](docs/PRIVACY.md) before building —
this tool analyzes information about real people, and contributions must keep
the consent gates, public-data-only design, and AI disclaimers intact.

## Workflow

1. Fork/clone, create a venv, `pip install -r requirements.txt`, copy
   `.env.example` → `.env` (set `XAI_API_KEY`; `X_BEARER_TOKEN` optional).
2. Initialize the DB: `python scripts/init_db.py && python scripts/migrate_v2_x.py`
3. Run tests before and after your change: `python tests/test_*.py`
   (offline; no API keys needed).
4. Open a PR against `main` with a clear description.

Maintainer deploys: `main` → staging (`dev.match-forge.com`), `v*.*.*` tags →
production (`match-forge.com`). See `infrastructure/deploy/RUNBOOK.md`.

## Secrets

- Never commit `.env`, tokens, or live API keys — `.gitignore` covers `.env`;
  `.env.example` documents every variable with placeholders.
- Rotate credentials via `infrastructure/deploy/credential-rotation.md`.

## Code standards

- Surgical changes only; match existing FastAPI + Jinja patterns.
- All LLM calls go through `app/services/llm_service.py`; all X API calls
  through `app/services/x_api_service.py`.
- Legal gates (`/legal/accept`), per-verification consent, and billing
  webhooks must not be bypassed.
- No scraping of X — official API + Grok server-side tools only.

## Support

Open a GitHub issue. Do not include personal data, screenshots of real
profiles, or credentials in issues.
