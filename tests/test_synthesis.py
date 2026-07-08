#!/usr/bin/env python3
"""Consolidated 2-call pipeline tests (mocked LLM — no network)."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import llm_service, trust_service
from app.services.trust_service import build_trust_result


def _profile():
    return SimpleNamespace(
        id=1,
        name="Jane",
        username=None,
        age=29,
        bio="Hiker, dog mom, taco enthusiast",
        location="Denver",
        platform="tinder",
        vision_analysis={"green_flags": ["detailed bio"], "red_flags": [], "confidence": 0.8},
        extracted_data={},
    )


def _pref():
    return SimpleNamespace(
        traits={}, weights={"compatibility": 0.4, "attractiveness": 0.3, "red_flags": 0.3}
    )


PHOTOS = [
    {
        "analysis_status": "analyzed",
        "photo_path": "data/uploads/1/screenshot_0.jpg",
        "authenticity_score": 82.0,
        "naturalness_score": 74.0,
        "ai_generated_likelihood": 8.0,
        "filter_heaviness": 20.0,
    }
]


def _run_synthesis(monkeypatch, fake_generate):
    monkeypatch.setattr(llm_service, "generate_json", fake_generate)
    return asyncio.run(
        trust_service.synthesize_profile_assessment(
            profile=_profile(),
            photo_analyses=PHOTOS,
            bio="Hiker, dog mom, taco enthusiast",
            profile_metadata={},
            social_enrichments=[],
            preference=_pref(),
            user_gender="male",
            user_intentions=["ltr"],
            ui_context={},
            user_profile=None,
        )
    )


def test_synthesis_success_parses_all_three_sections(monkeypatch):
    async def fake(prompt, **kwargs):
        return {
            "bot": {"bot_risk_score": 18, "signals": [], "explanation": "Human."},
            "catfish": {
                "catfish_risk_score": 12,
                "authenticity_score": 85,
                "consistency_score": 90,
                "social_mismatch": False,
                "risk_factors": [],
                "trust_explanation": "Looks genuine.",
            },
            "ranking": {
                "compatibility_score": 78,
                "attractiveness_score": 70,
                "red_flag_score": 10,
                "explanation": "Strong fit.",
            },
        }, None

    result = _run_synthesis(monkeypatch, fake)
    assert result["bot"]["analysis_status"] == "analyzed"
    assert result["catfish"]["analysis_status"] == "analyzed"
    # single photo → consistency must be nulled even if the model returned one
    assert result["catfish"]["consistency_score"] is None
    # overall computed deterministically from the user's weights
    expected = round(78 * 0.4 + 70 * 0.3 + (100 - 10) * 0.3, 1)
    assert result["ranking"]["overall_score"] == expected
    assert "AI" in result["ranking"]["explanation"] or "probabilistic" in result[
        "ranking"
    ]["explanation"], "disclaimer appended"


def test_synthesis_failure_degrades_each_section_honestly(monkeypatch):
    async def fake(prompt, **kwargs):
        raise RuntimeError("xAI down")

    result = _run_synthesis(monkeypatch, fake)
    assert result["bot"]["analysis_status"] == "heuristic"
    # heuristic catfish derives from REAL photo forensics
    assert result["catfish"]["analysis_status"] == "heuristic"
    assert result["catfish"]["authenticity_score"] == 82.0
    # ranking falls back to the labeled rule-based scorer with weighted overall
    assert "fallback" in result["ranking"]["explanation"]
    assert 0 <= result["ranking"]["overall_score"] <= 100


def test_synthesis_with_no_analyzed_photos_reports_unavailable(monkeypatch):
    async def fake(prompt, **kwargs):
        return {
            "bot": {"bot_risk_score": 20, "signals": []},
            "catfish": {"catfish_risk_score": 55, "authenticity_score": 40},
            "ranking": {
                "compatibility_score": 60,
                "attractiveness_score": 60,
                "red_flag_score": 20,
            },
        }, None

    monkeypatch.setattr(llm_service, "generate_json", fake)
    result = asyncio.run(
        trust_service.synthesize_profile_assessment(
            profile=_profile(),
            photo_analyses=[{"analysis_status": "unavailable"}],
            bio="hi",
            profile_metadata={},
            social_enrichments=[],
            preference=_pref(),
            user_gender="male",
            user_intentions=["ltr"],
            ui_context={},
            user_profile=None,
        )
    )
    # the model never saw analyzable photos — its catfish verdict is discarded
    assert result["catfish"]["analysis_status"] == "unavailable"
    assert result["catfish"]["catfish_risk_score"] is None


def test_build_trust_result_aggregates_and_statuses():
    bot = {"bot_risk_score": 15.0, "signals": [], "analysis_status": "analyzed"}
    catfish = {
        "catfish_risk_score": 10.0,
        "authenticity_score": None,
        "consistency_score": None,
        "risk_factors": [],
        "analysis_status": "analyzed",
        "trust_explanation": "ok",
    }
    trust = build_trust_result(PHOTOS, bot, catfish)
    # authenticity falls back to the photo average when catfish omits it
    assert trust["authenticity_score"] == 82.0
    assert trust["naturalness_score"] == 74.0
    assert trust["dimension_status"]["photos"] == "analyzed"

    degraded = build_trust_result(
        [{"analysis_status": "unavailable"}], bot, catfish
    )
    assert degraded["authenticity_score"] is None
    assert degraded["dimension_status"]["photos"] == "unavailable"


if __name__ == "__main__":
    print("Run via pytest (uses monkeypatch fixture).")
