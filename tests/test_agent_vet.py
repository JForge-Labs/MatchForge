#!/usr/bin/env python3
"""Agent vetting intent detection."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.agent_service import _VET_RE, estimate_agent_cost


def test_vet_prompt_detected():
    assert _VET_RE.search("please deep vet this person")
    assert _VET_RE.search("look them up on linkedin")


def test_multi_image_upload_includes_deep_vet_cost():
    cost = estimate_agent_cost("", image_count=3, url_count=0)
    # 3 profile images + rank refresh baseline
    assert cost >= 3


if __name__ == "__main__":
    test_vet_prompt_detected()
    test_multi_image_upload_includes_deep_vet_cost()
    print("All agent vet tests passed.")