# MatchForge — internal development

**Private repository.** Access is limited to authorized operators only. Do not publish credentials, customer data, or production URLs in issues or commits.

## Workflow

1. Develop on CT108 (`/opt/matchforge`) or local clone with venv.
2. Run tests: `python tests/test_*.py`
3. Push `main` → staging (`dev.match-forge.com`).
4. Tag `v*.*.*` → production (`match-forge.com`).

See `infrastructure/deploy/RUNBOOK.md` and `PROJECT_INSTRUCTIONS.md` for environment IDs and secrets handling.

## Secrets

- Never commit `.env` or live API keys.
- Stripe, xAI, SMTP, and DB credentials live in DO App Platform env or `~/.grok/secrets/`.
- Rotate via `infrastructure/deploy/credential-rotation.md`.

## Code standards

- Surgical changes only; match existing FastAPI + Jinja patterns.
- Karpathy guidelines: `~/.claude/skills/karpathy-guidelines/SKILL.md`
- Legal gates (`/legal/accept`) and billing webhooks must not be bypassed in production paths.

## Support

Internal operators only. User-facing support email is configured in Stripe and app env (`SMTP_FROM`).