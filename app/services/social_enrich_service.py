"""Public social media enrichment via web search (works without Playwright)."""
import logging
import re
from urllib.parse import quote_plus

import httpx

from app.core.config import get_settings
from app.models.profile import Profile, SocialEnrichment
from app.services.profile_extract_service import build_enrichment_query

logger = logging.getLogger(__name__)
settings = get_settings()

PLATFORM_SITE_QUERIES = {
    "facebook": "site:facebook.com",
    "instagram": "site:instagram.com",
    "linkedin": "site:linkedin.com/in",
    "x": "site:x.com OR site:twitter.com",
    "tiktok": "site:tiktok.com",
}

PLATFORM_URL_PATTERNS = {
    "facebook": re.compile(r"facebook\.com/(?!pages/|groups/)([\w.\-]+)", re.I),
    "instagram": re.compile(r"instagram\.com/([\w.]+)", re.I),
    "linkedin": re.compile(r"linkedin\.com/in/([\w\-]+)", re.I),
    "x": re.compile(r"(?:x\.com|twitter\.com)/([\w]+)", re.I),
    "tiktok": re.compile(r"tiktok\.com/@([\w.\-]+)", re.I),
}

PLATFORM_PROFILE_URLS = {
    "facebook": "https://facebook.com/{username}",
    "instagram": "https://instagram.com/{username}",
    "linkedin": "https://linkedin.com/in/{username}",
    "x": "https://x.com/{username}",
    "tiktok": "https://tiktok.com/@{username}",
}


async def _search_via_web(platform: str, query: str) -> dict:
    """DuckDuckGo HTML search — no browser required (prod-safe)."""
    site = PLATFORM_SITE_QUERIES.get(platform)
    if not site:
        return {"platform": platform, "status": "unsupported", "snippets": [], "usernames": []}

    search_query = f"{site} {query}"
    search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(search_query)}"
    findings: dict = {
        "platform": platform,
        "search_url": search_url,
        "snippets": [],
        "usernames": [],
        "query": search_query,
    }

    try:
        async with httpx.AsyncClient(
            timeout=25.0,
            follow_redirects=True,
            headers={"User-Agent": "MatchForge-Enrich/1.0"},
        ) as client:
            resp = await client.get(search_url)
            resp.raise_for_status()
            html = resp.text

        pattern = PLATFORM_URL_PATTERNS.get(platform)
        for block in re.findall(r'class="result__snippet"[^>]*>([^<]+)<', html)[:8]:
            snippet = block.strip()[:400]
            findings["snippets"].append(snippet)
            if pattern:
                for match in pattern.finditer(snippet):
                    user = match.group(1)
                    if user.lower() not in ("pages", "groups", "profile.php"):
                        findings["usernames"].append(user)

        for link in re.findall(r'class="result__a"[^>]*href="([^"]+)"', html)[:10]:
            if pattern:
                match = pattern.search(link)
                if match:
                    findings["usernames"].append(match.group(1))

        findings["usernames"] = list(dict.fromkeys(findings["usernames"]))[:5]
        findings["status"] = "ok" if findings["snippets"] or findings["usernames"] else "empty"
    except Exception as exc:
        logger.warning("Web enrich search failed for %s: %s", platform, exc)
        findings["status"] = "error"
        findings["error"] = str(exc)

    return findings


async def _search_via_playwright(platform: str, query: str) -> dict:
    """Optional browser search for dev environments with Playwright installed."""
    from urllib.parse import quote_plus as qp

    urls = {
        "x": f"https://x.com/search?q={qp(query)}&src=typed_query&f=user",
        "instagram": f"https://www.google.com/search?q=site:instagram.com+{qp(query)}",
        "linkedin": f"https://www.google.com/search?q=site:linkedin.com/in+{qp(query)}",
    }
    url_template = urls.get(platform)
    if not url_template:
        return {"platform": platform, "status": "unsupported", "snippets": [], "usernames": []}

    findings: dict = {"search_url": url_template, "snippets": [], "usernames": []}
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url_template, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)
            if platform == "x":
                for art in (await page.query_selector_all('[data-testid="UserCell"]'))[:5]:
                    text = await art.inner_text()
                    findings["snippets"].append(text[:300])
                    handle = re.search(r"@(\w+)", text)
                    if handle:
                        findings["usernames"].append(handle.group(1))
            else:
                for res in (await page.query_selector_all("div.g"))[:5]:
                    text = await res.inner_text()
                    findings["snippets"].append(text[:300])
            await browser.close()
        findings["status"] = "ok"
    except Exception as exc:
        logger.info("Playwright enrich skipped for %s: %s", platform, exc)
        findings["status"] = "error"
        findings["error"] = str(exc)
    return findings


async def search_platform(platform: str, query: str) -> dict:
    """Public entry for platform-specific web search."""
    if not query or query.strip().lower() in ("unknown",):
        return {"platform": platform, "status": "skipped", "snippets": [], "usernames": []}
    return await _search_platform(platform, query)


async def _search_platform(platform: str, query: str) -> dict:
    findings = await _search_via_web(platform, query)
    if findings.get("status") == "ok" and (findings.get("snippets") or findings.get("usernames")):
        return findings
    if platform in ("x", "instagram", "linkedin"):
        pw = await _search_via_playwright(platform, query)
        if pw.get("snippets") or pw.get("usernames"):
            return pw
    return findings


def _profile_url(platform: str, username: str | None, search_url: str | None) -> str | None:
    if username and platform in PLATFORM_PROFILE_URLS:
        return PLATFORM_PROFILE_URLS[platform].format(username=username)
    return search_url


def _summarize_findings(platform: str, findings: dict) -> str:
    usernames = findings.get("usernames", [])
    snippets = findings.get("snippets", [])
    if usernames:
        return f"Found potential {platform} profile(s): {', '.join(usernames[:3])}"
    if snippets:
        return f"Web search returned {len(snippets)} hint(s) — review linked results."
    return f"No public {platform} matches for this query."


async def enrich_profile(
    profile: Profile, platforms: list[str] | None = None
) -> list[SocialEnrichment]:
    """Search public social platforms and return enrichment records."""
    from app.services.profile_extract_service import default_enrich_platforms

    platforms = platforms or default_enrich_platforms(profile)
    query = build_enrichment_query(profile)
    if not query:
        query = (profile.name or "").strip()
    enrichments: list[SocialEnrichment] = []

    for platform in platforms:
        findings = await _search_platform(platform, query)
        username = (findings.get("usernames") or [None])[0]
        if not username and platform == (profile.platform or "").lower():
            username = profile.username

        enrichment = SocialEnrichment(
            profile_id=profile.id,
            platform=platform,
            username=username,
            url=_profile_url(platform, username, findings.get("search_url")),
            summary=_summarize_findings(platform, findings),
            findings=findings,
        )
        enrichments.append(enrichment)

    return enrichments