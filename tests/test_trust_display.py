#!/usr/bin/env python3
"""Trust card link deduplication tests."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.trust_display import trust_card_context


def _profile(**kwargs):
    defaults = {
        "trust_analysis": {},
        "social_enrichments": [],
        "extracted_data": {},
        "username": None,
        "platform": None,
        "enrichment_status": "done",
        "authenticity_score": 80,
        "naturalness_score": 80,
        "catfish_risk_score": 10,
        "bot_risk_score": 10,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _ranking(**kwargs):
    defaults = {
        "authenticity_score": 80,
        "naturalness_score": 80,
        "catfish_risk_score": 10,
        "bot_risk_score": 10,
        "trust_explanation": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_hides_source_when_same_url_in_enrichment():
    enrichment = SimpleNamespace(
        platform="facebook",
        url="https://facebook.com/jane.smith",
    )
    profile = _profile(
        platform="facebook",
        username="jane.smith",
        extracted_data={"profile_url": "https://facebook.com/jane.smith"},
        social_enrichments=[enrichment],
    )
    ctx = trust_card_context(profile, _ranking())
    assert ctx["source_url"] is None
    assert len(ctx["enrichments"]) == 1


def test_keeps_source_when_enrichment_differs():
    enrichment = SimpleNamespace(
        platform="instagram",
        url="https://instagram.com/jane.smith",
    )
    profile = _profile(
        platform="facebook",
        username="jane.smith",
        extracted_data={"profile_url": "https://facebook.com/jane.smith"},
        social_enrichments=[enrichment],
    )
    ctx = trust_card_context(profile, _ranking())
    assert ctx["source_url"] == "https://facebook.com/jane.smith"
    assert len(ctx["enrichments"]) == 1