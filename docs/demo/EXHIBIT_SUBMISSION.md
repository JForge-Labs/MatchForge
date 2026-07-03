# X Developer EXhibit — Submission Kit

Submission happens in the [X Developer Console](https://developer.x.com/)
(EXhibit / showcase section). Copy-paste material below.

## App name

**MatchForge — X-Verified Dating Intelligence**

## One-liner

Paste a dating-app screenshot or an @handle — Grok agentically cross-examines
their public X footprint and scores how real they are, with citations.

## Categories

Analytics & Insights · Bots & Automation · Developer Tools

## Description (~100 words)

Catfish and bots are epidemic on dating apps, and X is the largest public
behavioral record on the internet. MatchForge fuses the official X API v2
(user lookup, timelines, recent search) with Grok's server-side `x_search`
agentic tool to verify dating matches in 30 seconds: deterministic signals
(account age, follower health, posting cadence) blend 50/50 with Grok's
cited, multi-step investigation into an X Social Proof Score. The scoring
rubric updates itself weekly from live scam-tactic discussion on X. Users get
claim-by-claim verdicts, cross-platform photo checks, AI-generated
verification questions, and opt-in shareable badges. Public data only,
open source (MIT).

## What makes the X + Grok usage creative

1. **Two-path X integration** — official API for deterministic ground truth,
   Grok `x_search` for the qualitative agentic sweep; each covers the other's
   blind spots, and the app degrades gracefully to Grok-only without an X key.
2. **Self-updating threat model** — a weekly Grok `x_search` job distills
   trending romance-scam tactics from X and injects them into every scoring
   prompt. X itself keeps the detector current.
3. **Transparent agent** — the UI streams the tool-call trace (every X/web
   query Grok ran) plus citations; verification is auditable, not a black box.
4. **Closing the loop on X** — verified users post their badge back to X via
   an intent link with a server-rendered OG card.

## Links

- Live app: https://match-forge.com
- Repo: https://github.com/JForge-Labs/MatchForge
- Demo video: *(record per DEMO_SCRIPT below, upload, link here)*

## Demo script (for the video / GIFs)

1. Dashboard → drag in a dating screenshot → trust badges appear (10s)
2. Type a match's @handle in the tile → consent check → **agent trace panel
   fills with live x_search/web_search queries** (the wow shot, 20s)
3. Report lands: verdict pill, X Social Proof 0–100, claim checks with
   evidence, citations (10s)
4. "Get verification questions" → three grounded questions appear (5s)
5. "Share badge" → public report page + OG card → post-to-X intent (10s)

## Submission checklist

- [ ] X API keys attached to a project in the Developer Console (pay-per-use credits loaded)
- [ ] Repo public with this docs set
- [ ] Demo video recorded and linked
- [ ] Post announcing launch, tagging @XDevelopers (see LAUNCH_THREAD.md)
