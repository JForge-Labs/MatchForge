# MatchForge v0.1

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.1-green.svg)](https://fastapi.tiangolo.com/)

> Self-hosted, privacy-first AI dating intelligence toolbox.
> Drag in screenshots → local vision + ranking → trust scoring → percolated shortlist. All on your hardware.

**Self-host on your own hardware** — clone and follow Quickstart below. No cloud dependency.

## Project Charter

**Vision:** A self-hosted, local-first AI dating intelligence toolbox. Users drag in screenshots or enter usernames. The system immediately establishes a user profile (gender + dating intentions), builds a personalized preference vector, ranks and percolates matches accordingly, and enriches with public social data — all processed locally in this LXC.

**Core Philosophy:**
- **Screenshot-first** — universal input, no platform API drama
- **Privacy-first** — your data stays in your DB; LLM calls use xAI Grok (configurable)
- **Toolbox model** — simple drag-and-drop workflow for real users
- **Iterative R&D** — narrow MVP now; JSON exports, Playwright connectors, multi-user later

## Smart User Profiling (Onboarding)

On first use (or via **Settings → Update profile**), MatchForge captures:

- **Gender:** Male / Female / Non-binary / Prefer not to say
- **Intentions (multi-select):** LTR, Marriage, Casual, Hookups, Friendship, Undecided, Other
- **Optional liked-profile screenshots** — AI infers taste from examples you find appealing

This generates a rich **embedding-based preference vector** (traits, weights, ui_context) that drives all ranking, percolation, red-flag detection, and explanation tone. Examples:

- Straight male seeking LTR → high compatibility/red-flag weights, values-focused explanations
- Woman seeking casual → higher attractiveness weight, chemistry-focused openers

## Safety & Trust Layer

MatchForge scores every profile for authenticity before percolation:

| Signal | Score | What it detects |
|--------|-------|-----------------|
| **Authenticity** | 0–100 ↑ | Real person vs AI-generated / stolen photos |
| **Naturalness** | 0–100 ↑ | Minimal filters vs heavy FaceApp/beauty editing |
| **Catfish Risk** | 0–100 ↓ | AI faces, photo inconsistency, social mismatches |
| **Bot Risk** | 0–100 ↓ | Generic bios, templates, low-effort/spam patterns |

Trust signals **penalize overall score and percolation priority**. High-risk profiles sink in the feed with clear explanations:

> *"High catfish risk — profile photos appear AI-generated"*

Social enrichment feeds back into catfish scoring (no public footprint, mismatched details).

Re-uploading the same person (same platform + username) **enriches the existing tile** instead of creating a duplicate. Run `python scripts/dedupe_profiles.py` to merge any legacy duplicates.

## MVP Features (this iteration)

| Feature | Endpoint / UI |
|---------|---------------|
| User onboarding + preference vector | `GET /onboarding`, `POST /onboarding/profile` |
| Onboarding status | `GET /onboarding/status` |
| Screenshot upload + trust analysis | `POST /toolbox/upload-screenshots` (requires onboarding) |
| Authenticity / catfish / filter / bot scores | Returned in upload response + dashboard badges |
| Personalized AI ranking | Automatic after upload, uses user vector + trust layer |
| Public social enrichment | `POST /profiles/enrich` (re-scores catfish risk) |
| Percolated shortlist dashboard | `GET /dashboard/percolated`, `/dashboard` |
| Feedback loop | `POST /profiles/feedback` |

## Tech Stack

| Layer | Choice |
|-------|--------|
| Backend | Python 3.12 + FastAPI + SQLAlchemy |
| DB | PostgreSQL 16 + pgvector |
| Cache | Redis 7 |
| AI | xAI Grok (`grok-4.3` vision + text) via `LLM_PROVIDER=xai` |
| Browser automation | Playwright (social enrichment) |
| Frontend | FastAPI templates + vanilla JS |

## Quickstart

```bash
cd /opt/matchforge && source venv/bin/activate

# One-time DB init + seed preference vector
python scripts/init_db.py

# Set xAI key in .env (see .env.example)
# LLM_PROVIDER=xai
# XAI_API_KEY=...

# Start API
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**URLs (replace `localhost` with your host IP or domain):**
- Onboarding: http://localhost:8000/onboarding
- Dashboard: http://localhost:8000/dashboard
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- LLM health: http://localhost:8000/health/llm

## Onboarding Flow

1. Open http://localhost:8000/onboarding (or `/dashboard` — redirects if not complete).
2. Select gender and dating intentions.
3. Optionally upload liked-profile example screenshots.
4. Click **Build My Preference Vector** — Grok generates traits, weights, and ui_context.
5. You're redirected to the personalized dashboard.

**API test (no examples):**
```bash
curl -X POST http://127.0.0.1:8000/onboarding/profile \
  -F "gender=male" \
  -F 'intentions=["ltr","casual"]'
curl http://127.0.0.1:8000/onboarding/status
```

## Screenshot Usage Guide

1. Complete onboarding first.
2. Open `/dashboard` in your browser.
3. Drag one or more dating-app screenshots onto the drop zone (Tinder, Bumble, Hinge, etc.).
3. Click **Analyze & Rank** — each image is sent to Grok vision for extraction + trust scoring.
4. Extracted fields: name, username, age, bio, location, prompts, interests, red/green flags.
5. The ranking engine scores compatibility, attractiveness, and red flags against your preference vector.
6. Results appear in the **Percolated Shortlist**, sorted by priority score.
7. Click **Enrich** to queue public social search (X, Instagram, LinkedIn).
8. Use **Like / Pass / Top** buttons to feed back into percolation priority.

Screenshots are saved under `data/uploads/<profile_id>/`.

## Sample Vision Prompt

The vision service sends this prompt to Grok vision (see `app/services/vision_service.py`):

```
Analyze this dating app profile screenshot. Extract all visible information.
Return JSON with: name, username, age, bio, location, platform, prompts,
interests, photos_description, red_flags, green_flags, attractiveness_notes, confidence.
```

## Sample Ranking Prompt

The ranking service sends profile + preference vector + trust signals to Grok:

```
Score this profile against the user's preferences.
Return JSON with: compatibility_score, attractiveness_score, red_flag_score,
overall_score, explanation, conversation_starters, key_strengths, key_concerns.
```

## Preference Vector

Seeded by `scripts/init_db.py` with default traits:

- **Values:** kindness, intellectual curiosity, emotional availability
- **Lifestyle:** active, social, travel-friendly
- **Dealbreakers:** dishonesty, contempt, substance abuse
- **Weights:** compatibility 45%, attractiveness 25%, red flags 30%

Customize via direct DB edit or future settings UI.

## LLM System Prompts

| Stage | Location | Purpose |
|-------|----------|---------|
| Liked-example inference | `onboarding_service.py` | Infer taste from example screenshots |
| Preference vector generation | `onboarding_service.py` | Build traits/weights/ui_context from gender + intentions + examples |
| Personalized ranking | `ranking_service.py` | Score candidates for this specific user + trust penalties |
| Context-aware vision | `vision_service.py` | Flag red/green signals relative to user goals |
| Authenticity / AI detection | `vision_service.py` | Real vs AI-generated photos |
| Filter / editing detection | `vision_service.py` | FaceApp, beauty filters, enhancers |
| Catfish synthesis | `trust_service.py` | Photos + bio + social footprint consistency |
| Bot / fake text detection | `trust_service.py` | Generic bios, templates, spam patterns |

## Example Trust Output

```json
{
  "authenticity_score": 42,
  "naturalness_score": 35,
  "catfish_risk_score": 78,
  "bot_risk_score": 55,
  "trust_explanation": "High catfish risk — photos appear AI-generated. Bot risk: Generic templated bio.",
  "trust_badge": "red",
  "risk_factors": ["Heavy beauty filters detected", "No public social footprint found"]
}
```

## Trust Testing

```bash
cd /opt/matchforge && source venv/bin/activate
python scripts/migrate_trust.py          # add trust columns
python tests/generate_samples.py         # create sample screenshots
python tests/test_trust.py               # unit tests (no LLM)
python tests/test_profile_merge.py       # dedup / merge helpers
python scripts/dedupe_profiles.py        # merge legacy duplicate tiles

# Live upload with trust breakdown
curl -X POST http://127.0.0.1:8000/toolbox/upload-screenshots \
  -F "files=@tests/samples/filtered_generic_profile.jpg"
```

## API Endpoints

```
GET  /onboarding/status            # check if onboarding complete
POST /onboarding/profile           # gender + intentions + optional example images
GET  /onboarding                   # onboarding UI
POST /toolbox/upload-screenshots   # multipart file upload (requires onboarding)
POST /profiles/enrich              # {"profile_ids": [1], "platforms": ["x","instagram"]}
GET  /profiles/{id}                # single profile detail
POST /profiles/feedback            # {"ranking_id": 1, "feedback": "like"}
GET  /dashboard/percolated         # JSON shortlist
GET  /dashboard                  # HTML UI
GET  /health /health/db /health/llm
```

## Container Services

Native (host):
- PostgreSQL 16 — `matchforge_dev` / user `matchforge` / pgvector enabled
- Redis 7 — `redis://localhost:6379/0`
Optional docker-compose stack (offset ports for isolation):
```bash
docker compose up -d   # postgres:5433, redis:6380
```

## Resource Recommendations

Grok API calls are pay-per-use (~12 tokens per screenshot upload). Dev CT runs fine on 4 GB RAM since inference is remote.

## Legal & Privacy

MatchForge is positioned as a **personal safety and basic due diligence tool**. Users upload screenshots of **publicly visible** dating profiles; the app performs AI analysis for authenticity, compatibility, and safety signals. We do not access private databases or non-public information.

| Document | URL (when app is running) |
|----------|---------------------------|
| Terms of Service | `/legal/terms` |
| Privacy Policy | `/legal/privacy` |
| Policy acceptance | `/legal/accept` (after sign-in) |
| Markdown sources | `static/legal/terms.md`, `static/legal/privacy.md` |

**Policy version:** `2026-06-08` (stored on `UserProfile.policies_accepted_at` / `policies_version`)

Users must accept Terms and Privacy before onboarding or uploads. Policies cover PIPEDA consent, public-source-only input, retention/deletion (including per-profile delete anytime), and AI limitation disclaimers on all trust/ranking outputs.

## Responsible Use

Profile data describes **real people who have not consented to external ranking**.
- Only ingest screenshots/data you are authorized to access
- Store everything locally (self-hosted) or in your account (hosted)
- Treat scores as private decision-support, not ground truth
- Respect platform Terms of Service for any enrichment
- Accept Terms & Privacy at `/legal/accept` before first use

## Project Layout

```
app/
  main.py              FastAPI entrypoint
  core/                config + db
  api/                 toolbox, profiles, dashboard, health
  models/              Profile, Ranking, PreferenceVector, SocialEnrichment
  schemas/             Pydantic request/response types
  services/            vision, ranking, trust, profile_merge, social enrichment
templates/             dashboard.html, onboarding.html
static/                CSS + JS
scripts/               init_db.py, migrate_trust.py, dedupe_profiles.py
tests/                 sample screenshots + trust/merge unit tests
data/uploads/          screenshot storage
```

## Status

v0.1 R&D — screenshot → onboarding → vision → trust layer → ranking → dashboard operational.

**Roadmap:** embeddings, JSON export, scheduled enrichment, multi-user auth. See [Issues](https://github.com/jfodchuk/MatchForge/issues).

## Author

[John Fodchuk](https://github.com/jfodchuk) — homelab builder, privacy-first self-hosted AI.