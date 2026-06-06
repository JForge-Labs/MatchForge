# MatchForge — DigitalOcean App Platform Runbook

## Environments (dev → stage → prod)

| Tier | Where | URL | DB | Deploy trigger | Status |
|------|-------|-----|----|----------------|--------|
| **Dev** | CT108 LXC (`matchforge-dev`) | http://REDACTED-LAN-IP/dashboard · Tailscale funnel | Local PG `matchforge_dev` | Manual (`systemctl restart matchforge`) | **Live** |
| **Stage** | DO App Platform `matchforge-dev` | https://dev.match-forge.com | Separate managed PG | `main` push → GH Actions `deploy-stage` | **Live** (`a41e0b2e-…`) |
| **Prod** | DO App Platform `matchforge` | https://match-forge.com | Managed PG `db` component | `v*` tag or manual GH Actions | **Live** |

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

**GitHub repo secrets (configured):**
- `DIGITALOCEAN_ACCESS_TOKEN` — DO API / registry login
- `DO_PROD_APP_ID` — `REDACTED-DO-PROD-APP-ID`

**GitHub secrets (staging):**
- `DO_DEV_APP_ID` — `REDACTED-DO-STAGE-APP-ID`

**Typical flows:**
1. **Local dev** — code on CT108, test with Grok (`LLM_PROVIDER=xai`), commit, `git push origin main`
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

Use when GitHub Actions is unavailable:

```bash
source ~/.grok/secrets/digitalocean.env
cd /opt/matchforge
docker build -t registry.digitalocean.com/matchforge/web:latest .
doctl registry login
docker push registry.digitalocean.com/matchforge/web:latest
doctl apps create-deployment REDACTED-DO-PROD-APP-ID
```

Env-only update:

```bash
source ~/.grok/secrets/digitalocean.env
source ~/.grok/secrets/matchforge-prod.env
/opt/matchforge/infrastructure/deploy/render-spec.sh /tmp/matchforge-deploy.yaml
doctl apps update REDACTED-DO-PROD-APP-ID --spec /tmp/matchforge-deploy.yaml
```

## Provision staging (one-time)

```bash
source ~/.grok/secrets/digitalocean.env
source ~/.grok/secrets/matchforge-prod.env
source ~/.grok/secrets/xai.env
TEMPLATE=/opt/matchforge/infrastructure/deploy/matchforge-dev.app.yaml
sed \
  -e "s|__SECRET_KEY__|${SECRET_KEY}|g" \
  -e "s|__AUTH_PASSWORD__|${AUTH_PASSWORD}|g" \
  -e "s|__SMTP_HOST__|${SMTP_HOST}|g" \
  -e "s|__SMTP_PORT__|${SMTP_PORT}|g" \
  -e "s|__SMTP_USER__|${SMTP_USER}|g" \
  -e "s|__SMTP_PASSWORD__|${SMTP_PASSWORD}|g" \
  -e "s|__SMTP_FROM__|${SMTP_FROM}|g" \
  -e "s|__SMTP_USE_TLS__|${SMTP_USE_TLS}|g" \
  -e "s|__XAI_API_KEY__|${XAI_API_KEY}|g" \
  "${TEMPLATE}" > /tmp/matchforge-dev.yaml
doctl apps create --spec /tmp/matchforge-dev.yaml
# Note the app ID → GitHub secret DO_DEV_APP_ID → uncomment deploy-dev in workflow
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