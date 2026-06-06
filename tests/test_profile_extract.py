#!/usr/bin/env python3
"""Profile extraction normalization tests (no Ollama)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.profile_extract_service import (
    build_enrichment_query_from_data,
    normalize_extracted_profile,
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


if __name__ == "__main__":
    test_facebook_username_from_url_in_bio()
    test_facebook_search_query_uses_quoted_name_without_username()
    test_unknown_name_falls_back_to_username()
    print("ok")