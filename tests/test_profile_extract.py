#!/usr/bin/env python3
"""Profile extraction normalization tests (no Ollama)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.profile_extract_service import (
    build_enrichment_query_from_data,
    extract_urls_from_text,
    normalize_extracted_profile,
    parse_social_profile_url,
    sanitize_profile_inferences,
)


def test_facebook_username_from_url_in_bio():
    raw = {
        "name": "Jane Smith",
        "username": "unknown",
        "platform": "facebook",
        "bio": "Lives in Austin — see m.facebook.com/jane.smith.austin",
    }
    out = normalize_extracted_profile(raw)
    assert out["username"] == "jane.smith.austin"
    assert out["platform"] == "facebook"
    assert out["profile_url"] == "https://facebook.com/jane.smith.austin"


def test_facebook_search_query_uses_quoted_name_without_username():
    q = build_enrichment_query_from_data(
        {"name": "Jane Smith", "platform": "facebook"},
        platform="facebook",
    )
    assert '"Jane Smith"' in q


def test_unknown_name_falls_back_to_username():
    out = normalize_extracted_profile(
        {"name": "unknown", "username": "cool.handle", "platform": "instagram"}
    )
    assert out["name"] == "cool.handle"


def test_extract_urls_from_text():
    text = "Check https://instagram.com/cool.handle and also https://x.com/someone."
    assert extract_urls_from_text(text) == [
        "https://instagram.com/cool.handle",
        "https://x.com/someone",
    ]


def test_sanitize_name_derived_lash_business_prefers_employer():
    raw = {
        "name": "Lashes",
        "employer": "Smith & Co Accounting",
        "work": "lash extension business",
        "bio": "CPA at Smith & Co Accounting. Austin, TX.",
        "platform": "facebook",
    }
    out = sanitize_profile_inferences(normalize_extracted_profile(raw))
    work = (out.get("work") or "").lower()
    assert "accounting" in work
    assert "lash" not in work


def test_parse_social_profile_url_instagram():
    parsed = parse_social_profile_url("https://www.instagram.com/cool.handle/")
    assert parsed["platform"] == "instagram"
    assert parsed["username"] == "cool.handle"
    assert parsed["profile_url"] == "https://instagram.com/cool.handle"


if __name__ == "__main__":
    test_facebook_username_from_url_in_bio()
    test_facebook_search_query_uses_quoted_name_without_username()
    test_unknown_name_falls_back_to_username()
    test_extract_urls_from_text()
    test_parse_social_profile_url_instagram()
    print("ok")