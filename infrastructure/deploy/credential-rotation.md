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
| DO Prod App ID | `a0817ef0-3412-4f03-858b-a89c987092ad` (`~/.grok/secrets/matchforge-do-deployment.env`) |
| DO Stage App ID | `a41e0b2e-3407-4ad7-aad7-a82e5b80495b` (`~/.grok/secrets/matchforge-dev-deployment.env`) |
| Prod URL | https://match-forge.com |
| Stage URL | https://dev.match-forge.com |
| Default hostname | DO App → Overview |