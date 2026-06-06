"""Public social media enrichment via Playwright search."""
import logging
import re
from urllib.parse import quote_plus

from playwright.async_api import async_playwright

from app.core.config import get_settings
from app.models.profile import Profile, SocialEnrichment

logger = logging.getLogger(__name__)
settings = get_settings()

PLATFORM_SEARCH_URLS = {
    "x": "https://x.com/search?q={query}&src=typed_query&f=user",
    "instagram": "https://www.google.com/search?q=site:instagram.com+{query}",
    "linkedin": "https://www.google.com/search?q=site:linkedin.com/in+{query}",
    "tiktok": "https://www.google.com/search?q=site:tiktok.com+{query}",
}


def _build_search_query(profile: Profile) -> str:
    parts = []
    if profile.username:
        parts.append(profile.username.lstrip("@"))
    if profile.name:
        parts.append(profile.name)
    if profile.location:
        parts.append(profile.location.split(",")[0])
    return " ".join(parts) if parts else "unknown"


async def _search_platform(platform: str, query: str) -> dict:
    """Use headless browser to find public profile hints."""
    url_template = PLATFORM_SEARCH_URLS.get(platform)
    if not url_template:
        return {"platform": platform, "status": "unsupported"}

    search_url = url_template.format(query=quote_plus(query))
    findings: dict = {"search_url": search_url, "snippets": [], "usernames": []}

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            )
            await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)

            if platform == "x":
                articles = await page.query_selector_all('[data-testid="UserCell"]')
                for art in articles[:5]:
                    text = await art.inner_text()
                    findings["snippets"].append(text[:300])
                    handle = re.search(r"@(\w+)", text)
                    if handle:
                        findings["usernames"].append(handle.group(1))
            else:
                results = await page.query_selector_all("div.g")
                for res in results[:5]:
                    text = await res.inner_text()
                    findings["snippets"].append(text[:300])
                    if platform == "instagram":
                        m = re.search(r"instagram\.com/([\w.]+)", text)
                        if m:
                            findings["usernames"].append(m.group(1))
                    elif platform == "linkedin":
                        m = re.search(r"linkedin\.com/in/([\w-]+)", text)
                        if m:
                            findings["usernames"].append(m.group(1))

            await browser.close()
        findings["status"] = "ok"
    except Exception as exc:
        logger.warning("Social search failed for %s: %s", platform, exc)
        findings["status"] = "error"
        findings["error"] = str(exc)

    return findings


def _summarize_findings(platform: str, findings: dict) -> str:
    usernames = findings.get("usernames", [])
    snippets = findings.get("snippets", [])
    if usernames:
        return f"Found potential {platform} account(s): {', '.join(usernames[:3])}"
    if snippets:
        return f"Search returned {len(snippets)} result(s) — review manually."
    return f"No public {platform} footprint found for this query."


async def enrich_profile(
    profile: Profile, platforms: list[str] | None = None
) -> list[SocialEnrichment]:
    """Search public social platforms and return enrichment records."""
    platforms = platforms or ["x", "instagram", "linkedin"]
    query = _build_search_query(profile)
    enrichments: list[SocialEnrichment] = []

    for platform in platforms:
        findings = await _search_platform(platform, query)
        username = (findings.get("usernames") or [None])[0]
        url = findings.get("search_url")
        if username and platform == "x":
            url = f"https://x.com/{username}"
        elif username and platform == "instagram":
            url = f"https://instagram.com/{username}"

        enrichment = SocialEnrichment(
            profile_id=profile.id,
            platform=platform,
            username=username,
            url=url,
            summary=_summarize_findings(platform, findings),
            findings=findings,
        )
        enrichments.append(enrichment)

    return enrichments