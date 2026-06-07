"""Share payload includes referral link and signed token round-trip."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.share_service import (
    SHARE_VIEW_TTL_SECONDS,
    build_share_url,
    create_share_token,
    format_share_text,
    is_share_preview_bot,
    is_share_view_expired,
    verify_share_token,
)


def test_share_token_roundtrip():
    token = create_share_token(7, 42)
    assert verify_share_token(token) == (7, 42)
    assert verify_share_token("bad.token") is None


def test_share_text_includes_referral():
    class P:
        id = 1
        name = "Alex"
        username = None

    class R:
        id = 42
        overall_score = 72.0
        compatibility_score = 80.0
        attractiveness_score = 65.0
        red_flag_score = 20.0
        trust_explanation = "Looks genuine."
        explanation = "Good compatibility signals."

    trust = {"overall_trust": 78.0, "catfish_risk": 15.0, "auth": 85.0, "risk_factors": []}
    text = format_share_text(
        P(),
        R(),
        trust,
        share_url="https://match-forge.com/share/abc",
        referral_url="https://match-forge.com/signup?ref=xyz99",
    )
    assert "https://match-forge.com/signup?ref=xyz99" in text
    assert "https://match-forge.com/share/abc" in text
    assert "Alex" not in text
    assert "AI trust vetting" in text


def test_share_view_expiry_window():
    recent = datetime.now(timezone.utc) - timedelta(seconds=SHARE_VIEW_TTL_SECONDS - 30)
    stale = datetime.now(timezone.utc) - timedelta(seconds=SHARE_VIEW_TTL_SECONDS + 1)
    assert is_share_view_expired(recent) is False
    assert is_share_view_expired(stale) is True


def test_share_preview_bot_detection():
    assert is_share_preview_bot("facebookexternalhit/1.1") is True
    assert is_share_preview_bot("Mozilla/5.0 Chrome/120.0.0.0") is False


if __name__ == "__main__":
    test_share_token_roundtrip()
    test_share_text_includes_referral()
    test_share_view_expiry_window()
    test_share_preview_bot_detection()
    print("ok")