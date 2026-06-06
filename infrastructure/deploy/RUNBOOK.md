# MatchForge — DigitalOcean App Platform Runbook

## Stack

- **Runtime:** FastAPI + uvicorn on port 8000 (Dockerfile)
- **DB:** DO managed PostgreSQL 16 + pgvector (`db` component)
- **Region:** `tor1`
- **Domain:** `match-forge.com` (+ `www` alias)

## Deploy / update (DOCR — current)

GitHub is not linked to DigitalOcean yet; prod deploys from **DO Container Registry**.

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

To switch to GitHub deploy later: link GitHub in DO console, revert `matchforge.app.yaml` to `github:` + `dockerfile_path`, push.

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

- **No local Ollama** on App Platform — screenshot vision/ranking requires a remote `OLLAMA_BASE_URL` or returns degraded health on `/health/ollama`.
- **Ephemeral disk** — uploaded screenshots do not persist across container restarts without external object storage (future work).

## Secrets rotation

See `credential-rotation.md`.