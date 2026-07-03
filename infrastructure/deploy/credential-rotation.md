# MatchForge credential rotation (production)

Store live values in a chmod-600 secrets file outside the repo (path is your
choice — `render-spec.sh` documents its default convention). Never commit
secrets or paste real values into this file.

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
2. Update your local secrets file and the `DIGITALOCEAN_ACCESS_TOKEN` GitHub Actions secret
3. Re-auth `doctl auth init` if needed

## Record

| Item | Location |
|------|----------|
| DO Prod / Stage App IDs | Maintainer's private ops doc (not in this repo) |
| Prod URL | https://match-forge.com |
| Stage URL | https://dev.match-forge.com |
| Default hostname | DO App → Overview |