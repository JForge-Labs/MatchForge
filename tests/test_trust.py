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


def test_high_catfish_lowers_percolation():
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
    assert adjusted["percolation_priority"] < 30


if __name__ == "__main__":
    test_bot_heuristic_generic_bio_stays_moderate()
    test_trust_badges()
    test_high_catfish_lowers_percolation()
    print("All trust tests passed.")