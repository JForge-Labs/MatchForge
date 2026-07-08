#!/usr/bin/env python3
"""Quick trust-layer unit tests (heuristics, no Ollama required)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.trust_service import (
    _fallback_bot_risk,
    _trust_badge,
    compute_trust_adjusted_scores,
)


def test_bot_heuristic_generic_bio_stays_moderate():
    result = _fallback_bot_risk("Love to laugh! Partner in crime. Here for a good time.")
    assert result["bot_risk_score"] <= 45
    assert result["bot_risk_score"] >= 20
    assert any("Common" in s or "Generic" in s for s in result["signals"])


def test_trust_badges():
    assert _trust_badge(80) == "green"
    assert _trust_badge(50) == "yellow"
    assert _trust_badge(20) == "red"
    assert _trust_badge(80, invert=True) == "red"


def test_high_catfish_gates_the_match_score():
    base = {
        "overall_score": 80,
        "compatibility_score": 75,
        "attractiveness_score": 85,
        "red_flag_score": 10,
        "explanation": "Looks great.",
    }
    trust = {
        "authenticity_score": 30,
        "naturalness_score": 25,
        "catfish_risk_score": 85,
        "bot_risk_score": 40,
        "trust_explanation": "High catfish risk — photos appear AI-generated",
    }
    adjusted = compute_trust_adjusted_scores(base, trust)
    assert adjusted["overall_score"] < base["overall_score"]
    # catfish ≥ 70 caps the match at the gate value
    assert adjusted["overall_score"] <= 35
    # sort order equals the displayed score — no invisible divergence
    assert adjusted["percolation_priority"] == adjusted["overall_score"]
    assert adjusted["fit_score"] == 80
    assert adjusted["trust_penalty"] == round(80 - adjusted["overall_score"], 1)


def test_low_risk_applies_no_penalty():
    base = {"overall_score": 72.0, "explanation": ""}
    trust = {"catfish_risk_score": 20, "bot_risk_score": 15}
    adjusted = compute_trust_adjusted_scores(base, trust)
    assert adjusted["overall_score"] == 72.0
    assert adjusted["trust_penalty"] == 0


def test_missing_trust_dimensions_apply_no_penalty():
    base = {"overall_score": 64.0, "explanation": ""}
    adjusted = compute_trust_adjusted_scores(base, {})
    assert adjusted["overall_score"] == 64.0
    assert adjusted["catfish_risk_score"] is None
    assert adjusted["bot_risk_score"] is None


def test_adjustment_is_idempotent_on_reapplication_of_fit():
    """Re-running the adjustment from the same fit gives the same match."""
    base = {"overall_score": 70.0, "explanation": ""}
    trust = {"catfish_risk_score": 55, "bot_risk_score": 20}
    first = compute_trust_adjusted_scores(base, trust)
    second = compute_trust_adjusted_scores(base, trust)
    assert first["overall_score"] == second["overall_score"]


if __name__ == "__main__":
    test_bot_heuristic_generic_bio_stays_moderate()
    test_trust_badges()
    test_high_catfish_gates_the_match_score()
    test_low_risk_applies_no_penalty()
    test_missing_trust_dimensions_apply_no_penalty()
    test_adjustment_is_idempotent_on_reapplication_of_fit()
    print("All trust tests passed.")