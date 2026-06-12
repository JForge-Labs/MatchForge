"""Normalize vision extraction for dating and social profile screenshots."""
import re

PLATFORM_ALIASES = {
    "fb": "facebook",
    "meta": "facebook",
    "twitter": "x",
}

USERNAME_URL_PATTERNS = [
    (r"(?:https?://)?(?:www\.|m\.)?facebook\.com/(?!pages/|groups/|events/|watch/|photo\.php|profile\.php|share/|story\.php)([\w.\-]+)", "facebook"),
    (r"(?:https?://)?(?:www\.)?instagram\.com/([\w.]+)", "instagram"),
    (r"(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/([\w]+)", "x"),
    (r"(?:https?://)?(?:www\.)?linkedin\.com/in/([\w\-]+)", "linkedin"),
    (r"(?:https?://)?(?:www\.)?tiktok\.com/@([\w.\-]+)", "tiktok"),
]

URL_IN_TEXT_RE = re.compile(r"https?://[^\s<>\"']+", re.I)

FACEBOOK_RESERVED = {
    "pages", "groups", "events", "watch", "marketplace", "gaming",
    "profile.php", "photo.php", "story.php", "share", "login",
    "help", "policies", "privacy", "settings",
}


def _clean_username(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lstrip("@").strip("/")
    if not value or value.lower() in ("unknown", "null", "none", "n/a"):
        return None
    if value.lower() in FACEBOOK_RESERVED:
        return None
    return value


def _username_from_urls(*urls: str | None) -> tuple[str | None, str | None]:
    for raw in urls:
        if not raw:
            continue
        for pattern, platform in USERNAME_URL_PATTERNS:
            match = re.search(pattern, raw, re.I)
            if match:
                username = _clean_username(match.group(1))
                if username:
                    return username, platform
    return None, None


def _collect_strings(data: object) -> list[str]:
    """Gather all string values from nested vision JSON for URL scanning."""
    found: list[str] = []
    if isinstance(data, str):
        found.append(data)
    elif isinstance(data, dict):
        for val in data.values():
            found.extend(_collect_strings(val))
    elif isinstance(data, list):
        for item in data:
            found.extend(_collect_strings(item))
    return found


def _normalize_token(value: str | None) -> str | None:
    if not value:
        return None
    token = value.strip().lower()
    if not token or token in ("unknown", "null", "none", "n/a"):
        return None
    return token


def _significant_words(text: str) -> list[str]:
    return [w for w in re.split(r"\W+", text.lower()) if len(w) > 3]


def _work_supported_by_visible_text(work: str, visible: str) -> bool:
    """True when most significant words from work appear in visible profile text."""
    if not work:
        return True
    words = _significant_words(work)
    if not words:
        return True
    matches = sum(1 for word in words if word in visible)
    return matches >= max(1, len(words) // 2)


def _name_echoes_work(work: str, name: str | None, username: str | None) -> bool:
    """Detect occupation guesses that echo the display name/handle."""
    work_low = work.lower()
    for token in (name, username):
        if not token or len(token) < 4:
            continue
        stem = token[: max(4, len(token) - 1)]
        if stem in work_low or token in work_low:
            return True
    return False


def sanitize_profile_inferences(data: dict) -> dict:
    """Drop name-derived employer guesses when explicit employer text exists."""
    result = dict(data)
    visible = _merge_text_fields(result).lower()
    visible += "\n" + "\n".join(_collect_strings(result)).lower()

    employer = (result.get("employer") or "").strip()
    job_title = (result.get("job_title") or "").strip()
    work = (result.get("work") or "").strip()
    name = _normalize_token(result.get("name"))
    username = _normalize_token(result.get("username"))

    if employer and not work:
        work = employer
    elif employer and job_title:
        work = f"{job_title} at {employer}"
    elif employer:
        work = employer

    if work:
        unsupported = not _work_supported_by_visible_text(work, visible)
        name_guess = _name_echoes_work(work, name, username)
        if unsupported or name_guess:
            if employer and _work_supported_by_visible_text(employer, visible):
                work = f"{job_title} at {employer}".strip(" at ") if job_title else employer
            elif employer:
                work = employer
            elif unsupported and name_guess:
                work = ""
            elif name_guess:
                work = ""

    if work:
        result["work"] = work
    else:
        result.pop("work", None)
    if employer:
        result["employer"] = employer
    if job_title:
        result["job_title"] = job_title
    return result


def _merge_text_fields(data: dict) -> str:
    chunks: list[str] = []
    for key in (
        "bio", "about", "work", "employer", "job_title",
        "education", "hometown", "relationship_status",
    ):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            chunks.append(val)
    for prompt in data.get("prompts") or []:
        if isinstance(prompt, str):
            chunks.append(prompt)
    return "\n".join(chunks)


def normalize_extracted_profile(data: dict) -> dict:
    """Fill gaps after vision — especially Facebook usernames and platform."""
    result = dict(data)

    platform = (result.get("platform") or "other").lower()
    platform = PLATFORM_ALIASES.get(platform, platform)
    result["platform"] = platform

    scan_text = _merge_text_fields(result) + "\n" + "\n".join(_collect_strings(result))
    url_username, url_platform = _username_from_urls(
        result.get("profile_url"),
        result.get("url"),
        scan_text,
    )
    if url_platform and result.get("platform") in ("other", None, ""):
        result["platform"] = url_platform
    if url_platform == "facebook" or result.get("platform") == "facebook":
        result["platform"] = "facebook"

    username = _clean_username(result.get("username"))
    if not username:
        username = _clean_username(result.get("handle"))
    if not username:
        username = _clean_username(result.get("vanity_name"))
    if not username and url_username:
        username = url_username
    result["username"] = username

    name = (result.get("name") or "").strip()
    if not name or name.lower() in ("unknown", "null", "none"):
        name = username or None
    result["name"] = name

    if not result.get("bio"):
        merged = _merge_text_fields(result)
        if merged:
            result["bio"] = merged[:2000]

    if username and not result.get("profile_url") and result.get("platform") == "facebook":
        result["profile_url"] = f"https://facebook.com/{username}"

    return sanitize_profile_inferences(result)


def build_enrichment_query_from_data(data: dict, *, platform: str | None = None) -> str:
    """Build a search query from extracted vision data (pre-profile)."""
    parts: list[str] = []

    username = _clean_username(data.get("username"))
    if username:
        parts.append(username)

    name = (data.get("name") or "").strip()
    if name and name.lower() not in ("unknown", "null", "none"):
        if platform == "facebook" and not username:
            parts.append(f'"{name}"')
        else:
            parts.append(name)

    plat = platform or data.get("platform")
    if plat and plat != "other":
        parts.append(plat)

    for key in ("work", "education", "hometown", "location"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.split(",")[0].strip())

    seen: set[str] = set()
    unique = []
    for p in parts:
        low = p.lower()
        if low not in seen:
            seen.add(low)
            unique.append(p)

    return " ".join(unique)


def build_enrichment_query(profile) -> str:
    """Best-effort search query from profile + extracted vision data."""
    data = profile.extracted_data or {}
    platform = profile.platform or data.get("platform")
    query = build_enrichment_query_from_data(
        {**data, "name": profile.name or data.get("name"), "username": profile.username or data.get("username")},
        platform=platform,
    )
    return query or ""


async def enrich_extracted_profile(data: dict) -> dict:
    """Run quick public search to backfill username/platform gaps after vision."""
    from app.services import social_enrich_service

    result = dict(data)
    platform = (result.get("platform") or "other").lower()

    if not _clean_username(result.get("username")) and (
        platform == "facebook" or result.get("name") or result.get("bio")
    ):
        query = build_enrichment_query_from_data(result, platform="facebook")
        if query:
            findings = await social_enrich_service.search_platform("facebook", query)
            usernames = findings.get("usernames") or []
            if usernames:
                result["username"] = usernames[0]
                result["platform"] = "facebook"
                if not result.get("profile_url"):
                    result["profile_url"] = f"https://facebook.com/{usernames[0]}"
                result["enrichment_hint"] = {
                    "platform": "facebook",
                    "query": query,
                    "usernames": usernames[:3],
                    "snippets": (findings.get("snippets") or [])[:2],
                }

    return normalize_extracted_profile(result)


def extract_urls_from_text(text: str) -> list[str]:
    """Pull http(s) URLs from free text (paste, prompts, drag-drop)."""
    if not text:
        return []
    seen: set[str] = set()
    urls: list[str] = []
    for match in URL_IN_TEXT_RE.finditer(text):
        url = match.group(0).rstrip(".,);]>\"'")
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def parse_social_profile_url(url: str) -> dict | None:
    """Return platform/username/canonical profile URL when URL matches a social pattern."""
    username, platform = _username_from_urls(url)
    if not username or not platform:
        return None
    canonical = {
        "facebook": f"https://facebook.com/{username}",
        "instagram": f"https://instagram.com/{username}",
        "linkedin": f"https://linkedin.com/in/{username}",
        "x": f"https://x.com/{username}",
        "tiktok": f"https://tiktok.com/@{username}",
    }.get(platform, url.strip())
    return {
        "platform": platform,
        "username": username,
        "profile_url": canonical,
        "source_url": url.strip(),
    }


def default_enrich_platforms(profile) -> list[str]:
    platform = (profile.platform or "").lower()
    if platform == "facebook":
        return ["facebook", "instagram", "linkedin", "x"]
    if platform in ("instagram", "linkedin", "x", "tiktok"):
        return [platform, "facebook", "instagram", "linkedin"]
    return ["facebook", "instagram", "linkedin", "x"]