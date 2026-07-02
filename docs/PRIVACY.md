# Privacy Design

MatchForge processes information about real people who did not ask to be
analyzed. That responsibility shapes every feature.

## Principles

1. **Public data only.** The X verification channel touches exclusively public
   X data via the official API and Grok's `x_search` tool. No DMs, no private
   or protected content (protected accounts are never timeline-fetched), no
   scraping.
2. **User-initiated, always.** Nothing is looked up in the background. Every
   verification requires the user to submit a handle and check an explicit
   consent line stating what will be fetched.
3. **Deleted with the profile.** Verification reports live on the profile row;
   deleting a profile (or the whole account) removes them, associated
   evidence, and uploads. The `x_profiles` cache holds only public account
   metadata with a 24-hour TTL.
4. **Private by default, public by opt-in.** Reports are visible only to the
   checking user. The public badge page (`/verify/{token}`) renders only after
   the owner explicitly hits "Share badge", which sets a `share_enabled` flag —
   and shows only the X handle, verdict, score, and public signals. No dating
   platform, no photos, no location.
5. **Decision-support, not ground truth.** Every score is probabilistic. The
   UI and shared reports carry disclaimers; the tool is personal safety due
   diligence, not a background check.

## Consent gates in the product

- Terms + privacy acceptance before onboarding (`/legal/accept`)
- First-upload acknowledgement of the right to analyze submitted screenshots
- Per-verification public-data consent checkbox (tile form and handle lookup)
- Opt-in share action for any public report

## Data inventory (X features)

| Data | Where | Lifetime |
|---|---|---|
| X user object (public) | `x_profiles.user_data` | 24h TTL cache, refreshed on demand |
| Recent public posts | `x_profiles.timeline` | same |
| Verification report | `profiles.x_verification` | until profile/account deletion |
| Threat brief | `data/threat_brief.json` | aggregate tactics only — no personal data |

## Platform terms

v2 replaced the legacy Playwright X-scrape fallback with the official X API
and Grok tools — the entire X path is now ToS-clean by construction.
