# MatchForge

**Private · commercial · privacy-first**

MatchForge is a personal safety and due-diligence tool for dating. Users upload publicly visible profile screenshots; AI scores authenticity, compatibility, and safety signals into a private shortlist. Hosted at [match-forge.com](https://match-forge.com).

> **Internal repository.** Access is limited to authorized operators. See `CONTRIBUTING.md` and `PROJECT_INSTRUCTIONS.md`.

## Product charter

- **Screenshot-first** — universal input, no brittle platform APIs
- **Privacy-first** — user data stays in our managed infrastructure; scores are private decision-support only
- **Prepaid tokens** — free signup grant, Stripe top-ups, referral rewards on first paid top-up
- **Responsible use** — public-source-only input; not a background check or ground truth about anyone

## Stack

- **Backend:** FastAPI, PostgreSQL 16 + pgvector, Redis (configured)
- **AI:** xAI Grok (vision + ranking)
- **Payments:** Stripe Checkout (dynamic top-up amounts)
- **Deploy:** DigitalOcean App Platform (`main` → staging, `v*` tags → production)

## Operator quickstart (CT108 / dev)

```bash
cd /opt/matchforge && source venv/bin/activate
cp .env.example .env   # fill secrets locally only
python scripts/init_db.py
sudo systemctl restart matchforge
```

See `infrastructure/deploy/RUNBOOK.md` for staging and production deploy.

## Smart user profiling (onboarding)

On first use (or via profile settings), MatchForge captures:

- **Gender:** Male / Female
- **Intentions (multi-select):** LTR, Marriage, Casual, Hookups, Friendship, Undecided, Other
- **Optional:** name, profile photo, age, location, bio, liked-profile examples

This generates a **preference vector** that drives ranking, percolation, and explanation tone.

## Safety & Trust Layer

MatchForge scores every profile for authenticity before percolation:

| Signal | Score | What it detects |
|--------|-------|-----------------|
| **Authenticity** | 0–100 ↑ | Real person vs AI-generated / stolen photos |
| **Naturalness** | 0–100 ↑ | Minimal filters vs heavy FaceApp/beauty editing |
| **Catfish Risk** | 0–100 ↓ | AI faces, photo inconsistency, social mismatches |
| **Bot Risk** | 0–100 ↓ | Generic bios, templates, low-effort/spam patterns |

Trust signals **penalize overall score and percolation priority**. High-risk profiles sink in the feed with clear explanations.

Social enrichment feeds back into catfish scoring (no public footprint, mismatched details).

<!-- Rest of README unchanged below - read from original for API sections if needed -->