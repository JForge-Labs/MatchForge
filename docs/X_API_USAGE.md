# X API Usage

Everything MatchForge does with X, in one place — for EXhibit reviewers and
self-hosters budgeting pay-per-use credits.

## Design principle: two complementary X data paths

1. **Official X API v2** — deterministic, billable ground truth. Facts that
   must be exact (account age, metrics, verified status) come from here.
2. **Grok's server-side `x_search` tool** — qualitative, agentic sweep. Things
   that need judgment (does this timeline read like a human? is anyone
   accusing this handle of catfishing?) come from here, with citations.

If `X_BEARER_TOKEN` is unset, verification degrades gracefully to the
Grok-only path — self-hosters get the full flow with just an xAI key.

## Official X API v2 endpoints

| Endpoint | Used for | Where |
|---|---|---|
| `GET /2/users/by/username/:username` | Account facts: `created_at`, `public_metrics`, `verified`, `verified_type`, `protected`, `profile_image_url`, bio, location | `x_api_service.lookup_user` |
| `GET /2/users/:id/tweets` | Recent timeline (≤ `X_TIMELINE_MAX_POSTS`, default 50) for cadence analysis, claim checking, and question generation | `x_api_service.fetch_timeline` |
| `GET /2/tweets/search/recent` | What *others* say about the handle (7-day window, impersonation/scam reports) | `x_api_service.search_mentions` |
| Profile image CDN | Full-size avatar for the vision photo cross-check | `x_api_service.fetch_profile_image` |

### Deterministic signals computed from API data (no LLM)

`x_api_service.compute_x_signals()` scores 0–100 from:

- Account age (5+ years strong positive; <90 days strong negative)
- Follower/following ratio (follow-farm pattern detection)
- Listed count, verified status, default avatar, empty bio
- Posting cadence from the timeline (burst posting → automation; natural cadence → positive; long dormancy → negative)
- Lifetime post volume anomalies; 100%-retweet timelines

### Cost control

- Every fetch is cached in the `x_profiles` table for `X_CACHE_TTL_HOURS`
  (default 24h) — repeat verifications of the same handle are free.
- A cold verification reads ~50 posts ≈ $0.25 at $0.005/read, priced into the
  internal token cost of the `x_verify` activity (`model_router.py`).
- X API credit purchases currently earn up to 20% back in xAI credits.

## Grok server-side tools (xAI Responses API)

| Tool | Used for | Where |
|---|---|---|
| `x_search` | Agentic verification sweep; weekly threat-intel brief; question generation fallback | `llm_service.generate_agentic` callers |
| `web_search` | Cross-platform corroboration (news, stolen-photo reports, people-search hits) | same |

The agentic loop runs server-side at xAI with `max_turns`
(`XAI_AGENT_MAX_TURNS`, default 8). MatchForge surfaces the **tool-call
trace** (every query Grok ran) and **citations** in the UI and in shared
reports — the investigation is transparent, not a black box.

## Post-to-X

Shared verification badges use the standard tweet intent URL
(`twitter.com/intent/tweet`) with an OG card (`/verify/{token}/badge.png`)
rendered server-side — no write-scope API access needed.

## Rate limits & responsible use

- User lookup and timelines sit far below the 900 req/15 min per-endpoint
  windows at MatchForge's scale; the cache keeps headroom.
- Only public data; protected accounts are never timeline-fetched.
- No streaming endpoints in the MVP (polling deltas is the roadmap item);
  filtered stream is the planned upgrade for real-time match monitoring.
