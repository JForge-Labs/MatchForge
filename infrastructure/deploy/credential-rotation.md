# MatchForge credential rotation (production)

Store live values in `~/.grok/secrets/matchforge-prod.env` (chmod 600). Never commit.

## SECRET_KEY (session cookies)

1. Generate: `openssl rand -hex 32`
2. Update DO App env `SECRET_KEY` (type: SECRET)
3. Redeploy — existing sessions invalidate (users re-login)

## AUTH_PASSWORD (single-user gate)

1. Generate: `openssl rand -base64 24`
2. Update DO App env `AUTH_PASSWORD`
3. Redeploy

## DATABASE_URL

Rotated automatically when DO DB credentials rotate. Re-render spec with component vars; never paste `${db.DATABASE_URL}`.

## DIGITALOCEAN_API_TOKEN

1. Revoke old token in DO Control Panel → API
2. Update `~/.grok/secrets/digitalocean.env`
3. Re-auth `doctl auth init` if needed

## Record

| Item | Location |
|------|----------|
| DO App ID | `infrastructure/deploy/deployment-state.env` (local only) |
| Prod URL | https://match-forge.com |
| Default hostname | DO App → Overview |