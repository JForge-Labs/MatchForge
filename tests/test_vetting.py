#!/usr/bin/env python3
"""Vetting helpers — no network required."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.vetting_service import _extract_social_links, check_location_consistency


def test_extract_social_links_from_urls():
    links = _extract_social_links(
        "Jane Doe linkedin.com/in/jane-doe works at Acme",
        "https://instagram.com/janedoe",
    )
    platforms = {link["platform"] for link in links}
    assert "linkedin" in platforms
    assert "instagram" in platforms


def test_location_consistency_mismatch():
    result = check_location_consistency(
        claimed_location="Austin, TX",
        bio="Lives in Denver, CO and loves hiking",
        extracted_data=None,
    )
    assert result["consistent"] is False


if __name__ == "__main__":
    test_extract_social_links_from_urls()
    test_location_consistency_mismatch()
    print("All vetting tests passed.")