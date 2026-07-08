#!/usr/bin/env python3
"""Deterministic fit combiner and trust-summary renormalization tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ranking_service import compute_fit_score
from app.services.vetting_service import compute_trust_summary


def test_fit_applies_user_weights_verbatim():
    scores = {
        "compatibility_score": 80,
        "attractiveness_score": 60,
        "red_flag_score": 20,
    }
    # Attractiveness weight zero → moving it must not change the fit
    weights = {"compatibility": 0.6, "attractiveness": 0.0, "red_flags": 0.4}
    fit = compute_fit_score(scores, weights)
    fit_hot = compute_fit_score({**scores, "attractiveness_score": 100}, weights)
    assert fit == fit_hot
    assert fit == round(80 * 0.6 + (100 - 20) * 0.4, 1)


def test_fit_renormalizes_partial_weights():
    scores = {
        "compatibility_score": 100,
        "attractiveness_score": 100,
        "red_flag_score": 0,
    }
    assert compute_fit_score(scores, {"compatibility": 2.0}) == 100.0
    assert compute_fit_score(scores, None) == 100.0


def test_fit_clamps_out_of_range_model_output():
    scores = {
        "compatibility_score": 150,
        "attractiveness_score": -20,
        "red_flag_score": "35",
    }
    fit = compute_fit_score(scores, None)
    assert 0 <= fit <= 100


def test_trust_summary_renormalizes_over_present_dimensions():
    full = compute_trust_summary(
        {
            "authenticity_score": 80,
            "naturalness_score": 80,
            "catfish_risk_score": 20,
            "bot_risk_score": 20,
            "consistency_score": 80,
        }
    )
    partial = compute_trust_summary(
        {
            "authenticity_score": 80,
            "naturalness_score": None,
            "catfish_risk_score": 20,
            "bot_risk_score": None,
            "consistency_score": None,
        }
    )
    # All present dims agree at 80 — missing dims must not drag the score
    assert full["overall_trust_score"] == 80.0
    assert partial["overall_trust_score"] == 80.0
    assert partial["confidence"]["tier"] == "low"


def test_trust_summary_none_when_nothing_analyzed():
    summary = compute_trust_summary({})
    assert summary["overall_trust_score"] is None
    assert summary["catfish_flag"] == "unknown"


def test_location_mismatch_is_hedged_not_a_flag_override():
    summary = compute_trust_summary(
        {
            "authenticity_score": 85,
            "naturalness_score": 80,
            "catfish_risk_score": 10,
            "bot_risk_score": 10,
            "consistency_score": 85,
        },
        {"location": {"consistent": False}},
    )
    # A regex heuristic must never paint the scariest label by itself
    assert summary["catfish_flag_label"] != "Catfish risk"
    assert any("worth asking" in f for f in summary["risk_factors"])


def test_empty_web_footprint_is_not_penalized():
    base_inputs = {
        "authenticity_score": 75,
        "naturalness_score": 70,
        "catfish_risk_score": 25,
        "bot_risk_score": 15,
        "consistency_score": 75,
    }
    with_empty_web = compute_trust_summary(
        base_inputs, {"web": {"status": "empty"}}
    )
    without = compute_trust_summary(base_inputs)
    assert with_empty_web["overall_trust_score"] == without["overall_trust_score"]


if __name__ == "__main__":
    test_fit_applies_user_weights_verbatim()
    test_fit_renormalizes_partial_weights()
    test_fit_clamps_out_of_range_model_output()
    test_trust_summary_renormalizes_over_present_dimensions()
    test_trust_summary_none_when_nothing_analyzed()
    test_location_mismatch_is_hedged_not_a_flag_override()
    test_empty_web_footprint_is_not_penalized()
    print("All scoring tests passed.")
