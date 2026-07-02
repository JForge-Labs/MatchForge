#!/usr/bin/env python3
"""X verification helpers — no network required."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime, timedelta, timezone

from app.services.x_api_service import compute_x_signals, normalize_handle
from app.services.x_verify_service import blend_social_proof, _build_claims
from app.services.threat_intel_service import format_brief_for_prompt, get_brief
from app.services.llm_service import _extract_citations, _extract_tool_trace
from app.services.vetting_service import compute_trust_summary


def test_normalize_handle():
    assert normalize_handle("@JaneDoe") == "JaneDoe"
    assert normalize_handle("jane_doe") == "jane_doe"
    assert normalize_handle("https://x.com/JaneDoe") == "JaneDoe"
    assert normalize_handle("https://twitter.com/@JaneDoe/") == "JaneDoe"
    assert normalize_handle("x.com/search") is None
    assert normalize_handle("not a handle!") is None
    assert normalize_handle("") is None
    assert normalize_handle("waytoolongforanxhandle") is None


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def test_compute_x_signals_established_account():
    now = datetime.now(timezone.utc)
    user = {
        "created_at": _iso(now - timedelta(days=6 * 365)),
        "verified": False,
        "protected": False,
        "description": "Runner, coffee snob, software person.",
        "profile_image_url": "https://pbs.twimg.com/profile_images/x_normal.jpg",
        "public_metrics": {
            "followers_count": 800,
            "following_count": 500,
            "tweet_count": 4200,
            "listed_count": 12,
        },
    }
    timeline = [
        {"created_at": _iso(now - timedelta(days=i * 3)), "text": f"post {i}"}
        for i in range(10)
    ]
    signals = compute_x_signals(user, timeline)
    assert signals["deterministic_score"] > 70
    assert signals["account_age_days"] > 5 * 365 - 2
    assert any("years old" in s for s in signals["signals"])


def test_compute_x_signals_new_bot_like_account():
    now = datetime.now(timezone.utc)
    user = {
        "created_at": _iso(now - timedelta(days=20)),
        "verified": False,
        "protected": False,
        "description": "",
        "profile_image_url": "https://abs.twimg.com/sticky/default_profile_images/default_profile.png",
        "public_metrics": {
            "followers_count": 3,
            "following_count": 2000,
            "tweet_count": 900,
            "listed_count": 0,
        },
    }
    timeline = [
        {"created_at": _iso(now - timedelta(hours=i)), "text": f"spam {i}"}
        for i in range(50)
    ]
    signals = compute_x_signals(user, timeline)
    assert signals["deterministic_score"] < 30
    assert any("new-account" in s for s in signals["signals"])
    assert any("follow-farm" in s.lower() for s in signals["signals"])


def test_blend_social_proof():
    assert blend_social_proof(80, 60) == 70.0
    assert blend_social_proof(None, 60) == 60.0
    assert blend_social_proof(80, None) == 80.0
    assert blend_social_proof(None, None) is None


def test_build_claims_drops_empty():
    class FakeProfile:
        name = "Jane"
        age = None
        location = "Austin, TX"
        bio = ""
        platform = "hinge"
        extracted_data = {"work": "Nurse at Ascension", "interests": ["running"]}

    claims = _build_claims(FakeProfile())
    assert claims["name"] == "Jane"
    assert claims["work"] == "Nurse at Ascension"
    assert "age" not in claims and "bio" not in claims


def test_threat_brief_seed_and_prompt_format():
    brief = get_brief()
    assert brief["tactics"], "seed brief must always provide tactics"
    text = format_brief_for_prompt(brief)
    assert "pig" in text.lower() or "tactic" in text.lower() or "-" in text


def test_trust_summary_with_x_proof():
    base = {
        "authenticity_score": 70,
        "naturalness_score": 70,
        "catfish_risk_score": 20,
        "bot_risk_score": 15,
        "consistency_score": 75,
    }
    without_x = compute_trust_summary(base)
    strong_x = compute_trust_summary({**base, "x_social_proof_score": 90})
    weak_x = compute_trust_summary({**base, "x_social_proof_score": 10})
    assert strong_x["overall_trust_score"] > without_x["overall_trust_score"]
    assert weak_x["overall_trust_score"] < without_x["overall_trust_score"]
    assert weak_x["catfish_flag"] == "caution"
    assert any("X" in f for f in weak_x["risk_factors"])
    assert strong_x["catfish_flag_label"] == "X-verified"


def test_extract_tool_trace_and_citations():
    body = {
        "citations": ["https://x.com/janedoe/status/1"],
        "output": [
            # Real xAI shape (custom_tool_call with named tool + JSON input)
            {
                "type": "custom_tool_call",
                "name": "x_keyword_search",
                "input": '{"query":"from:janedoe marathon","limit":"10"}',
                "status": "completed",
            },
            # Legacy/docs shape
            {"type": "web_search_call", "query": "janedoe austin nurse"},
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "{}",
                        "annotations": [
                            {"url": "https://x.com/janedoe"},
                            {"url": "https://x.com/janedoe/status/1"},
                        ],
                    }
                ],
            },
        ],
    }
    trace = _extract_tool_trace(body)
    assert [t["tool"] for t in trace] == ["x_keyword_search", "web_search"]
    assert trace[0]["query"] == "from:janedoe marathon"
    citations = _extract_citations(body)
    assert citations[0] == "https://x.com/janedoe/status/1"
    assert "https://x.com/janedoe" in citations
    assert len(citations) == 2  # deduped


if __name__ == "__main__":
    test_normalize_handle()
    test_compute_x_signals_established_account()
    test_compute_x_signals_new_bot_like_account()
    test_blend_social_proof()
    test_build_claims_drops_empty()
    test_threat_brief_seed_and_prompt_format()
    test_trust_summary_with_x_proof()
    test_extract_tool_trace_and_citations()
    print("All X verification tests passed.")
