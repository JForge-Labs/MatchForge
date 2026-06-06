# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Active development |

## Reporting a vulnerability

If you discover a security issue, **do not** open a public issue.

Email or DM the maintainer via GitHub (@jfodchuk) with:

- Description of the vulnerability
- Steps to reproduce
- Impact assessment

We aim to respond within 7 days.

## Secrets & deployment

- **Never** commit `.env`, PATs, or database credentials
- Copy `.env.example` → `.env` locally; chmod 600
- MatchForge processes sensitive personal data (dating profile screenshots) — run on infrastructure you control
- Keep Ollama, PostgreSQL, and Redis bound to **localhost** or a trusted network unless you add authentication
- Do not expose internal LAN IPs, hostnames, or infrastructure details in public issues or commits

## Responsible use

MatchForge is **local decision-support software**, not a surveillance or stalking tool. Do not use it to rank or profile people without authorization. See README responsible-use section.