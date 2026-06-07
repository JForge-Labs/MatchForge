"""Stripe billing helpers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.stripe_service import dollars_to_tokens, validate_topup_amount
from fastapi import HTTPException


def test_dollars_to_tokens_default_rate():
    assert dollars_to_tokens(10) == 200
    assert dollars_to_tokens(25) == 500


def test_validate_topup_minimum():
    assert validate_topup_amount(10) == 10
    try:
        validate_topup_amount(5)
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 400


if __name__ == "__main__":
    test_dollars_to_tokens_default_rate()
    test_validate_topup_minimum()
    print("ok")