# Grok Agent Design

MatchForge is Grok-exclusive for all reasoning and analysis. This doc covers
the agentic workflows added in v2.

## The agentic layer

`llm_service.generate_agentic()` wraps the xAI Responses API with server-side
tools:

```python
result = await llm_service.generate_agentic(
    prompt,
    model=settings.xai_text_reason,          # reasoning model
    tools=[{"type": "x_search"}, {"type": "web_search"}],
    max_turns=settings.xai_agent_max_turns,  # bounded tool loop (default 8)
)
# result.text        → final answer (JSON for our prompts)
# result.citations   → deduped source URLs from searches
# result.tool_trace  → [{tool, query, status}, ...] shown live in the UI
# result.response_id → for stateful continuation (previous_response_id)
```

xAI executes the entire reasoning/tool loop server-side: Grok analyzes the
task, issues X and web searches, iterates on results, and returns a final
answer with citations. MatchForge parses the output items to surface the
investigation trace — the "watch Grok investigate" demo moment.

## Agent 1 — X verification (`x_verify_service.X_VERIFY_PROMPT`)

**Model:** reasoning · **Tools:** `x_search` + `web_search` · **max_turns:** 8

Inputs assembled in the prompt:

- **CLAIMED IDENTITY** — structured claims extracted from dating screenshots
- **X ACCOUNT GROUND TRUTH** — official API facts + deterministic signals
- **RECENT X POSTS** — timeline sample (dated, truncated)
- **CURRENT SCAM TACTICS** — the live threat brief (see Agent 3)

The agent confirms handle ownership plausibility, marks each claim
supported/contradicted/unverifiable, and hunts red/green flags. Output is
strict JSON: verdict, score, claim checks, flags, confidence, one-liner.

**Scoring discipline:** Grok's qualitative score is blended 50/50 with the
deterministic Python score (`blend_social_proof`). The LLM never sees its own
number become the final answer — hard signals anchor it.

## Agent 2 — photo cross-check (`PHOTO_CROSS_CHECK_PROMPT`)

**Model:** vision · multi-image input: X profile photo first, dating photos after.
Returns same-person likelihood, identical-photo flag (stolen-avatar signal),
and a different-person red flag that applies a −25 penalty to the blended score.

## Agent 3 — threat intel (`threat_intel_service.THREAT_INTEL_PROMPT`)

**Model:** reasoning · **Tools:** `x_search` + `web_search` · scheduled weekly
(APScheduler, daily staleness check).

Asks Grok what romance-scam/catfish/bot tactics are trending on X in the last
14 days, returns structured `{tactic, indicators, example_phrasings}` JSON,
cached to `data/threat_brief.json` with citations. The brief is injected into:

- the X verification prompt (Agent 1)
- the catfish synthesis prompt (`trust_service.CATFISH_SYNTHESIS_PROMPT`)

so the scoring rubric literally updates itself from X. A static seed brief
ships in the repo for cold starts and keyless self-hosts.

## Agent 4 — verification questions (`VERIFICATION_QUESTIONS_PROMPT`)

**Model:** fast (when timeline data exists) or reasoning + `x_search`
(keyless fallback). Generates 3 date-appropriate questions only the real
account owner could answer, each with the expected genuine-answer signal —
never quoting posts verbatim or revealing the user researched them.

## Prompt conventions (repo-wide)

- All prompts demand **JSON-only** output; `parse_json_response()` tolerates
  markdown fences.
- Anti-hallucination rules are explicit: never infer employers from names,
  "unverifiable" is a valid outcome, judge only from found evidence.
- Model routing and internal token pricing live in
  `app/services/model_router.py` (`x_verify`, `verification_questions`,
  `x_monitor_check` activities).
