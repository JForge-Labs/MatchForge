# MatchForge — X-Verified Dating Intelligence

**Paste a screenshot or an @handle. Grok cross-examines their public X footprint and tells you if they're real — before you waste a week texting a bot.**

Built for the **[X Developer EXhibit](https://developer.x.com/exhibit)** · Categories: *Analytics & Insights · Bots & Automation · Developer Tools*

Hosted at [match-forge.com](https://match-forge.com) · MIT licensed · FastAPI + PostgreSQL + xAI Grok + X API v2

> Demo video: *(placeholder — see `docs/demo/`)*

---

## Using the hosted app

MatchForge is a hosted product — no install required. Sign up free at **[match-forge.com](https://match-forge.com)**, and every new account starts with a free grant of tokens to try it out. Tokens cover the pay-per-use costs of the xAI Grok and X API calls behind each analysis; buy more via Stripe if you use it heavily.

The code below is open source (MIT) for transparency and the X Developer EXhibit — you don't need to run any of it to use MatchForge.

## The problem

Catfish, bots, and stolen-photo profiles are epidemic on dating apps. Meanwhile, X is the largest public behavioral record on the internet — and Grok is the only model with native, server-side X search. MatchForge fuses both into a 30-second trust check.

## How it uses X + Grok (the EXhibit story)

Every feature below maps to a concrete X API endpoint or Grok capability — full details in [`docs/X_API_USAGE.md`](docs/X_API_USAGE.md) and [`docs/GROK_AGENTS.md`](docs/GROK_AGENTS.md).

| Feature | X API v2 | Grok |
|---|---|---|
| Screenshot → profile extraction | — | Vision (`grok-4.3`), JSON extraction |
| Trust layer (authenticity, catfish, bot, naturalness) | — | Vision + reasoning synthesis |
| **X Verification Channel** — verify any @handle | `GET /2/users/by/username`, `GET /2/users/:id/tweets`, recent search | Agentic run with server-side `x_search` + `web_search` tools (`max_turns` loop, citations) |
| **X Social Proof Score** — fifth trust dimension | Deterministic signals: account age, follower ratio, cadence, verified status | Qualitative judgment, blended 50/50 with the deterministic score |
| Photo cross-check | Profile image CDN | Multi-image vision comparison |
| **Trend-aware threat intel** — scoring rubric updates itself from X | — | Weekly `x_search` sweep of live scam-tactic discussion, injected into every catfish prompt |
| **AI verification questions** — things only the real person could answer | Timeline sample | Question generation grounded in public posts |
| Shareable verification badge | Post-to-X intent link | — |

The demo moment: type an @handle and **watch the agent trace live** — every `x_search` and `web_search` query Grok runs is surfaced in the UI with citations.

## Run it locally (for development)

This is for contributors who want to hack on the code — not required to use MatchForge (see [Using the hosted app](#using-the-hosted-app) above). Works with only an xAI key; the official X API is optional (Grok's `x_search` covers the no-key path).

```bash
git clone https://github.com/JForge-Labs/MatchForge && cd MatchForge
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # set XAI_API_KEY (required), X_BEARER_TOKEN (optional)
python scripts/init_db.py    # PostgreSQL 16 + pgvector
python scripts/migrate_v2_x.py
uvicorn app.main:app --reload
```

Open http://localhost:8000/dashboard, sign up, and either drop a dating-app screenshot or paste an X handle. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full dev workflow.

Tip: X API credit purchases currently earn up to 20% back in xAI API credits — one budget powers both halves of this app.

## Architecture

```
screenshot ──▶ Grok vision ──▶ trust pipeline ─┐
                                               ├─▶ ranked shortlist + trust badges
@handle ──▶ X API v2 (facts) ──┐               │
           Grok agentic x_search ┴─▶ X Social Proof Score + verification report
                    ▲
        weekly threat brief (Grok x_search)
```

Full diagram and module map: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

- **Backend:** FastAPI · PostgreSQL 16 + pgvector · SQLAlchemy
- **AI:** xAI Grok via the Responses API — vision, fast/reasoning text, and server-side agentic tools
- **X data:** official X API v2 (pay-per-use), TTL-cached in `x_profiles`
- **Frontend:** server-rendered Jinja + vanilla JS (screenshot-first, drag & drop)
- **Payments:** Stripe Checkout, prepaid token ledger

## Safety & Trust Layer

Five trust dimensions per profile:

| Signal | Score | What it detects |
|--------|-------|-----------------|
| **Authenticity** | 0–100 ↑ | Real person vs AI-generated / stolen photos |
| **Naturalness** | 0–100 ↑ | Minimal filters vs heavy FaceApp/beauty editing |
| **Catfish Risk** | 0–100 ↓ | AI faces, photo inconsistency, social mismatches, live scam-tactic matches |
| **Bot Risk** | 0–100 ↓ | Generic bios, templates, low-effort/spam patterns |
| **X Social Proof** | 0–100 ↑ | Account age, follower health, posting cadence, cross-platform claim checks |

High-risk profiles sink in the shortlist with cited, user-facing explanations.

## Privacy & responsible use

- **Public X data only**, fetched on explicit user action with an in-UI consent line — no DMs, no private data, no scraping (official API + Grok tools exclusively)
- Verification data is deleted with the profile/account (one-click delete)
- Reports are private by default; the public badge page requires the owner's explicit opt-in
- Decision-support only — AI scores are probabilistic, not ground truth about any person

Details: [`docs/PRIVACY.md`](docs/PRIVACY.md) · [`SECURITY.md`](SECURITY.md)

## Repo map

```
app/api/          FastAPI routers (x_verify.py = verification endpoints)
app/services/     llm_service (Grok + agentic tools) · x_api_service (X API v2)
                  x_verify_service (orchestrator) · threat_intel_service · trust_service
app/models/       SQLAlchemy models (x_profile.py = X data cache)
docs/             Architecture, X API usage, Grok agent design, privacy
scripts/          DB init/migrations, ops
templates/ static/  Server-rendered UI
tests/            Offline test suites (python tests/test_x_verify.py)
```

## License

MIT — see [`LICENSE`](LICENSE). Never commit secrets; `.env` is gitignored and `.env.example` documents every variable.
