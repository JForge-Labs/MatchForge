"""Affiliate program tests."""
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import SessionLocal
from app.models.account import Account
from app.models.affiliate import Affiliate, AffiliateCommission
from app.services import account_service, affiliate_service, stripe_service


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@affiliate-test.local"


def _create_affiliate(db, slug: str | None = None, email: str | None = None) -> Affiliate:
    slug = slug or f"aff-{uuid.uuid4().hex[:6]}"
    contact = email or _unique_email("partner")
    return affiliate_service.create_affiliate(
        db,
        slug=slug,
        name="Test Partner",
        contact_email=contact,
        commission_rate=Decimal("0.15"),
    )


def _affiliate_ref(db, affiliate: Affiliate) -> str:
    return affiliate_service.ensure_link_code(db, affiliate)


def test_build_affiliate_url():
    url = affiliate_service.build_affiliate_url("a8f3k2m9pq")
    assert url.endswith("/join/a8f3k2m9pq")
    assert "ri81" not in url
    assert "aff=" not in url


def test_signup_with_link_code_sets_attribution(db):
    affiliate = _create_affiliate(db)
    db.commit()
    ref = _affiliate_ref(db, affiliate)

    email = _unique_email("referred")
    status, _ = account_service.request_signup(db, email, affiliate_ref=ref)
    assert status == "sent"

    account = db.query(Account).filter(Account.email == email).first()
    assert account is not None
    assert account.referred_by_affiliate_id == affiliate.id


def test_self_referral_blocked(db):
    affiliate = _create_affiliate(db, email="partner@example.com")
    db.commit()

    status, _ = account_service.request_signup(
        db, "partner@example.com", affiliate_ref=_affiliate_ref(db, affiliate)
    )
    assert status == "sent"

    account = db.query(Account).filter(Account.email == "partner@example.com").first()
    assert account.referred_by_affiliate_id is None


def test_record_commission_at_15_percent(db):
    affiliate = _create_affiliate(db)
    db.commit()

    email = _unique_email("buyer")
    account_service.request_signup(db, email, affiliate_ref=_affiliate_ref(db, affiliate))
    db.commit()
    account = db.query(Account).filter(Account.email == email).first()

    row = affiliate_service.record_commission(
        db,
        account_id=account.id,
        stripe_ref=f"cs_test_{uuid.uuid4().hex}",
        topup_usd=20,
    )
    db.commit()

    assert row is not None
    assert row.gross_cents == 2000
    assert row.commission_cents == 300
    assert row.status == "pending"


def test_second_purchase_creates_second_commission(db):
    affiliate = _create_affiliate(db)
    db.commit()

    email = _unique_email("repeat")
    account_service.request_signup(db, email, affiliate_ref=_affiliate_ref(db, affiliate))
    db.commit()
    account = db.query(Account).filter(Account.email == email).first()

    affiliate_service.record_commission(
        db, account_id=account.id, stripe_ref=f"cs_a_{uuid.uuid4().hex}", topup_usd=10
    )
    affiliate_service.record_commission(
        db, account_id=account.id, stripe_ref=f"cs_b_{uuid.uuid4().hex}", topup_usd=25
    )
    db.commit()

    count = (
        db.query(AffiliateCommission)
        .filter(AffiliateCommission.referred_account_id == account.id)
        .count()
    )
    assert count == 2


def test_commission_idempotent_on_stripe_ref(db):
    affiliate = _create_affiliate(db)
    db.commit()

    email = _unique_email("idem")
    account_service.request_signup(db, email, affiliate_ref=_affiliate_ref(db, affiliate))
    db.commit()
    account = db.query(Account).filter(Account.email == email).first()

    ref = f"cs_idem_{uuid.uuid4().hex}"
    first = affiliate_service.record_commission(
        db, account_id=account.id, stripe_ref=ref, topup_usd=20
    )
    second = affiliate_service.record_commission(
        db, account_id=account.id, stripe_ref=ref, topup_usd=20
    )
    db.commit()

    assert first is not None
    assert second is not None
    assert first.id == second.id
    count = db.query(AffiliateCommission).filter(AffiliateCommission.stripe_ref == ref).count()
    assert count == 1


def test_inactive_affiliate_no_commission(db):
    affiliate = _create_affiliate(db)
    affiliate.is_active = False
    db.commit()

    email = _unique_email("inactive")
    account_service.request_signup(db, email, affiliate_ref=_affiliate_ref(db, affiliate))
    db.commit()
    account = db.query(Account).filter(Account.email == email).first()
    assert account.referred_by_affiliate_id is None


def test_mark_commissions_paid(db):
    affiliate = _create_affiliate(db)
    db.commit()

    email = _unique_email("paid")
    account_service.request_signup(db, email, affiliate_ref=_affiliate_ref(db, affiliate))
    db.commit()
    account = db.query(Account).filter(Account.email == email).first()

    row = affiliate_service.record_commission(
        db, account_id=account.id, stripe_ref=f"cs_paid_{uuid.uuid4().hex}", topup_usd=10
    )
    db.commit()

    updated = affiliate_service.mark_commissions_paid(
        db, [row.id], payout_note="PayPal test"
    )
    db.commit()
    db.refresh(row)

    assert updated == 1
    assert row.status == "paid"
    assert row.payout_note == "PayPal test"
    assert row.paid_at is not None


def test_stripe_credit_purchase_records_affiliate_commission(db):
    affiliate = _create_affiliate(db)
    db.commit()

    email = _unique_email("stripe")
    account_service.request_signup(db, email, affiliate_ref=_affiliate_ref(db, affiliate))
    db.commit()
    account = db.query(Account).filter(Account.email == email).first()

    ref = f"cs_hook_{uuid.uuid4().hex}"
    stripe_service.credit_purchase(
        db,
        account_id=account.id,
        tokens=200,
        stripe_ref=ref,
        topup_usd=10,
        kind="manual_topup",
    )

    comm = (
        db.query(AffiliateCommission)
        .filter(AffiliateCommission.stripe_ref == ref)
        .first()
    )
    assert comm is not None
    assert comm.commission_cents == 150


def test_affiliate_stats_url_hides_internal_slug(db):
    slug = f"hidden-{uuid.uuid4().hex[:8]}"
    affiliate = affiliate_service.create_affiliate(
        db,
        slug=slug,
        name="Partner",
        contact_email=f"hidden-{uuid.uuid4().hex[:8]}@partner.example.com",
        commission_rate=Decimal("0.15"),
    )
    db.commit()
    stats = affiliate_service.affiliate_stats(db, affiliate)
    assert stats["slug"] == slug
    assert slug not in stats["affiliate_url"]
    assert "/join/" in stats["affiliate_url"]


def test_mask_email():
    assert affiliate_service.mask_email("jane@example.com") == "j***@example.com"


def test_partner_dashboard_token_roundtrip(db):
    affiliate = _create_affiliate(db, slug=f"partner-{uuid.uuid4().hex[:8]}")
    db.commit()
    url = affiliate_service.build_partner_dashboard_url(affiliate.id)
    assert "/partner?token=" in url
    token = url.split("token=", 1)[1]
    assert affiliate_service.resolve_partner_token(token) == affiliate.id


def test_delete_test_affiliates(db):
    _create_affiliate(db)
    db.commit()
    before = affiliate_service.count_test_affiliates(db)
    assert before >= 1
    deleted = affiliate_service.delete_test_affiliates(db)
    db.commit()
    assert deleted >= 1
    assert affiliate_service.count_test_affiliates(db) == 0


def test_list_affiliates_excludes_test(db):
    real_slug = f"real-{uuid.uuid4().hex[:8]}"
    affiliate_service.create_affiliate(
        db,
        slug=real_slug,
        name="Real Partner",
        contact_email=f"real-{uuid.uuid4().hex[:8]}@partner.example.com",
        commission_rate=Decimal("0.15"),
    )
    _create_affiliate(db)
    db.commit()
    all_rows = affiliate_service.list_affiliates_with_stats(db, include_test=True)
    prod_rows = affiliate_service.list_affiliates_with_stats(db, include_test=False)
    assert len(all_rows) > len(prod_rows)
    assert any(r["slug"] == real_slug for r in prod_rows)
    assert all(r["name"] != "Test Partner" or not r["slug"].startswith("aff-") for r in prod_rows)
