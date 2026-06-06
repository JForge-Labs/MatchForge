# Contributing to MatchForge

Thanks for your interest. This project is in active R&D (v0.1).

## Before you start

1. Read the **responsible-use** section in README.md
2. Check [open issues](https://github.com/jfodchuk/MatchForge/issues) or the project Asana board (maintainer-managed)
3. Keep changes surgical — MatchForge follows Karpathy-style minimal diffs

## Development setup

```bash
git clone https://github.com/jfodchuk/MatchForge.git
cd MatchForge
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in locally, never commit
python scripts/init_db.py
python scripts/migrate_trust.py
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Requires PostgreSQL 16 + pgvector, Redis, and Ollama locally.

## Pull requests

- One logical change per PR
- No secrets, screenshots of real people, or live `.env` files
- Add tests when fixing bugs in `tests/`

## Code of conduct

Be respectful. This tool touches sensitive personal-data boundaries — contributors must uphold privacy-first principles.