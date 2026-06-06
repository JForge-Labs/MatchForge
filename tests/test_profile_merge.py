#!/usr/bin/env python3
"""Profile identity matching and merge helpers (no LLM)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.profile_merge_service import (
    dedupe_shortlist_rankings,
    find_existing_profile,
    identity_key,
    merge_analysis_into_profile,
)


class _FakeProfile:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeRanking:
    def __init__(self, profile, priority):
        self.profile = profile
        self.percolation_priority = priority


def test_identity_key_username():
    assert identity_key("facebook", "jane.doe", "Jane Doe") == "facebook:jane.doe"


def test_identity_key_name_fallback():
    assert identity_key("tinder", None, "Alex Kim") == "tinder:name:alex kim"


def test_dedupe_shortlist_keeps_best_priority():
    p1 = _FakeProfile(id=1, platform="facebook", username="same", name="A", extracted_data={})
    p2 = _FakeProfile(id=2, platform="facebook", username="same", name="A", extracted_data={})
    r1 = _FakeRanking(p1, 40)
    r2 = _FakeRanking(p2, 90)
    result = dedupe_shortlist_rankings([r1, r2])
    assert len(result) == 1
    assert result[0].percolation_priority == 90


def test_merge_analysis_appends_upload_history():
    profile = _FakeProfile(
        name="Old",
        username=None,
        bio="Short",
        age=None,
        location=None,
        platform="tinder",
        extracted_data={"red_flags": ["old"]},
        photos=[],
        vision_analysis={},
    )
    merge_analysis_into_profile(
        profile,
        {
            "name": "Old Name",
            "bio": "Much longer bio with more detail",
            "red_flags": ["new flag"],
            "platform": "bumble",
        },
        photo_path="data/uploads/1/s2.jpg",
        photo_index=1,
    )
    assert "new flag" in profile.extracted_data["red_flags"]
    assert len(profile.extracted_data["upload_history"]) == 1
    assert profile.bio.startswith("Much longer")


if __name__ == "__main__":
    test_identity_key_username()
    test_identity_key_name_fallback()
    test_dedupe_shortlist_keeps_best_priority()
    test_merge_analysis_appends_upload_history()
    print("All profile merge tests passed.")