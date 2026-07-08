#!/usr/bin/env python3
"""P3 memory features: dedup corroboration, score snapshots, history rows."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.profile_merge_service import _corroborates, _is_name_only_key, identity_key
from app.services.ranking_service import snapshot_ranking
from app.utils.trust_display import _analysis_history


def test_name_only_keys_detected():
    assert _is_name_only_key("tinder:name:sarah")
    assert _is_name_only_key("name:sarah")
    assert not _is_name_only_key("tinder:sarah_h")
    assert not _is_name_only_key(None)
    # sanity: identity_key still produces name-only keys without a username
    assert identity_key("tinder", None, "Sarah") == "tinder:name:sarah"


def _profile(age=29, location="Denver, CO"):
    return SimpleNamespace(age=age, location=location)


def test_name_only_merge_requires_age_and_location():
    # two different Sarahs: same name, different age → never merge
    assert not _corroborates(_profile(age=29), age=35, location="Denver, CO")
    # same age but different city → never merge
    assert not _corroborates(_profile(location="Denver, CO"), age=29, location="Austin, TX")
    # missing data is not corroboration
    assert not _corroborates(_profile(age=None), age=29, location="Denver, CO")
    assert not _corroborates(_profile(location=None), age=29, location="Denver, CO")
    # age within 1 AND matching location → merge allowed
    assert _corroborates(_profile(age=29), age=30, location="denver, co")
    # substring locations count ("Denver" vs "Denver, CO")
    assert _corroborates(_profile(location="Denver, CO"), age=29, location="Denver")


def _ranking(**kw):
    d = dict(
        overall_score=62.0,
        compatibility_score=75.0,
        attractiveness_score=68.0,
        red_flag_score=15.0,
        catfish_risk_score=18.0,
        score_history=[],
    )
    d.update(kw)
    return SimpleNamespace(**d)


def test_snapshot_appends_and_caps():
    r = _ranking()
    snapshot_ranking(r, "Note added")
    assert len(r.score_history) == 1
    entry = r.score_history[0]
    assert entry["trigger"] == "Note added"
    assert entry["overall"] == 62.0
    assert entry["at"]  # timestamped

    for i in range(30):
        r.overall_score = 50.0 + i
        snapshot_ranking(r, "Re-analysis")
    assert len(r.score_history) == 20  # capped

    # unscored rankings are never snapshotted
    empty = _ranking(overall_score=None)
    snapshot_ranking(empty, "x")
    assert empty.score_history == []


def test_analysis_history_rows_carry_deltas_newest_first():
    r = _ranking(
        overall_score=70.0,
        score_history=[
            {"at": "2026-07-01T10:00:00+00:00", "trigger": "New screenshot analyzed", "overall": 55.0},
            {"at": "2026-07-03T10:00:00+00:00", "trigger": "Deep vet", "overall": 62.0},
        ],
    )
    rows = _analysis_history(r)
    assert [row["trigger"] for row in rows] == [
        "Current",
        "Deep vet",
        "New screenshot analyzed",
    ]
    assert rows[0]["overall"] == 70.0 and rows[0]["delta"] == 8.0
    assert rows[1]["delta"] == 7.0
    assert rows[2]["delta"] is None
    assert rows[1]["at"] == "2026-07-03"

    # no history → no panel
    assert _analysis_history(_ranking()) == []


if __name__ == "__main__":
    test_name_only_keys_detected()
    test_name_only_merge_requires_age_and_location()
    test_snapshot_appends_and_caps()
    test_analysis_history_rows_carry_deltas_newest_first()
    print("All memory-feature tests passed.")
