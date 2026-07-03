# MatchForge — DigitalOcean App Platform Runbook

## Environments (dev → stage → prod)

| Tier | Where | URL | DB | Deploy trigger |
|------|-------|-----|----|----------------|
| **Dev** | Your local machine | http://localhost:8000/dashboard | Local PostgreSQL | Manual (`uvicorn app.main:app --reload`) |
| **Stage** | DO App Platform | https://dev.match-forge.com | Separate managed PG | `main` push → GH Actions `deploy-stage` |
| **Prod** | DO App Platform | https://match-forge.com | Managed PG `db` component | `v*` tag or manual GH Actions |

> Operator-specific values (DO app IDs, internal hosts, secrets file paths) live in
> the maintainer's private ops doc — not in this repository. Self-hosters can
> substitute their own DO App Platform apps and secrets management.

### CI/CD pipeline (`.github/workflows/deploy.yml`)

```
┌─────────────┐     push main / tag v* / workflow_dispatch
│   GitHub    │──────────────────────────────────────────────┐
└─────────────┘                                              │
                                                             ▼
                                                    ┌────────────────┐
                                                    │  build (GHA)   │
                                                    │ docker build   │
                                                    │ push DOCR      │
                                                    │ web:latest     │
                                                    └───────┬────────┘
                                                            │
              ┌─────────────────────────────────────────────┼──────────────────────────┐
              │                                             │                          │
              ▼                                             ▼                          ▼
     push main                                   tag v* OR manual                workflow_dispatch
     deploy-stage job                            deploy-prod job                 stage / prod
     dev.match-forge.com                         match-forge.com
     DO_DEV_APP_ID                               DO_PROD_APP_ID
```

> **Note:** `deploy_on_push` is disabled on both apps. GH Actions
> `create-deployment` is the only deploy trigger — this avoids racing
> deployments between DO's own image-push trigger and GH Actions.
```

**GitHub Actions repo secrets (required):**
- `DIGITALOCEAN_ACCESS_TOKEN` — DO API / registry login
- `DO_PROD_APP_ID` — your production App Platform app ID
- `DO_DEV_APP_ID` — your staging App Platform app ID

**Typical flows:**
1. **Local dev** — code locally, test with Grok (`LLM_PROVIDER=xai`), commit, `git push origin main`
2. **Stage auto-deploy** — every `main` push builds, pushes DOCR, and rolls out to `dev.match-forge.com`
3. **Prod release** — `git tag v0.1.2 && git push origin v0.1.2` **or** Actions → Deploy MatchForge → `deploy_target: prod`
4. **Manual stage** — Actions → `deploy_target: stage` (without waiting for a new build's stage job)

## Stack

- **Runtime:** FastAPI + uvicorn on port 8000 (Dockerfile)
- **DB:** DO managed PostgreSQL 16 + pgvector (`db` component)
- **AI:** xAI Grok via `LLM_PROVIDER=xai` (dev + prod)
- **Region:** `tor1`
- **Domain:** `match-forge.com` (+ `www` alias); stage target `dev.match-forge.com`

## Manual deploy (DOCR fallback)

Use when GitHub Actions is unavailable (`$DO_PROD_APP_ID` = your app ID):

```bash
export DIGITALOCEAN_ACCESS_TOKEN=...   # from your DO API token / secrets manager
docker build -t registry.digitalocean.com/matchforge/web:latest .
doctl registry login
docker push registry.digitalocean.com/matchforge/web:latest
doctl apps create-deployment "$DO_PROD_APP_ID"
```

Env-only update:

```bash
export DIGITALOCEAN_ACCESS_TOKEN=...
infrastructure/deploy/render-spec.sh matchforge.app.yaml /tmp/matchforge-deploy.yaml
doctl apps update "$DO_PROD_APP_ID" --spec /tmp/matchforge-deploy.yaml
```

`render-spec.sh` sources secrets from `~/.grok/secrets/*.env` by convention —
adjust to your own secrets manager.

## Provision staging (one-time)

> **Note:** staging (`matchforge-dev.app.yaml`) intentionally omits `X_BEARER_TOKEN`
> and runs X verification on the Grok-only `x_search` path — the official X API
> (pay-per-use) is enabled in **prod only** for the EXhibit. If you ever add the
> `__X_BEARER_TOKEN__` placeholder to the staging template, also add the matching
> `-e "s|__X_BEARER_TOKEN__|${X_BEARER_TOKEN:-}|g"` line to the sed below (or use
> `render-spec.sh matchforge-dev.app.yaml`, which already substitutes it).

```bash
export DIGITALOCEAN_ACCESS_TOKEN=...
infrastructure/deploy/render-spec.sh matchforge-dev.app.yaml /tmp/matchforge-dev.yaml
doctl apps create --spec /tmp/matchforge-dev.yaml
# Note the returned app ID → GitHub Actions secret DO_DEV_APP_ID
```

## Database init

`docker-entrypoint.sh` runs `scripts/init_db.py` in the background on container start (idempotent). Health checks pass while DB boots.

## DNS (match-forge.com)

At your registrar or Cloudflare (grey cloud / DNS only):

| Type | Name | Value |
|------|------|-------|
| CNAME | `@` or `match-forge.com` | `<app>-<id>.ondigitalocean.app` |
| CNAME | `www` | `<app>-<id>.ondigitalocean.app` |

Wait for DO domain phase `ACTIVE` in App → Settings → Domains.

## Verify

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://<default-hostname>/health
curl -sS -o /dev/null -w '%{http_code}\n' https://match-forge.com/health
```

## Rollback

```bash
doctl apps list-deployments <APP_ID>
doctl apps create-deployment <APP_ID> --deployment-id <prior-id>
```

## Prod limitations

- **No Playwright** on App Platform — social enrichment degrades to HTTP/search.
- **Ephemeral disk** — uploaded screenshots do not persist across container restarts without external object storage (future work).
- **Grok API** — pay-per-use; set `XAI_API_KEY` in app env (via `render-spec.sh`).

## Secrets rotation

See `credential-rotation.md`.