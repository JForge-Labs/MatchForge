#!/usr/bin/env python3
"""Referral program unit tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.referral_service import (
    REFERRAL_FIRST_TOPUP_FOUNDER_EXTRA,
    REFERRAL_FIRST_TOPUP_REFERRER_TOKENS,
    _referrer_first_topup_payout,
    build_referral_url,
)


class FakeAccount:
    def __init__(self, is_founder=False):
        self.is_founder = is_founder


def test_referral_url():
    url = build_referral_url("abc12")
    assert "ref=abc12" in url
    assert url.endswith("ref=abc12") or "ref=abc12" in url


def test_first_topup_payout_regular():
    assert (
        _referrer_first_topup_payout(FakeAccount())
        == REFERRAL_FIRST_TOPUP_REFERRER_TOKENS
    )


def test_first_topup_payout_founder():
    expected = REFERRAL_FIRST_TOPUP_REFERRER_TOKENS + REFERRAL_FIRST_TOPUP_FOUNDER_EXTRA
    assert _referrer_first_topup_payout(FakeAccount(is_founder=True)) == expected


if __name__ == "__main__":
    test_referral_url()
    test_first_topup_payout_regular()
    test_first_topup_payout_founder()
    print("ok")