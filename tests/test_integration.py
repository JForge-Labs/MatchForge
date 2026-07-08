#!/usr/bin/env python3
"""Integration tests over the money and ownership paths (matchforge_test DB).

Covers what the unit suite cannot: the real signup→verify→session flow,
cross-account IDOR on profile endpoints, concurrent charge integrity
(SELECT FOR UPDATE), and Stripe double-credit idempotency.
"""
import re
import sys
import threading
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.db import Base, get_db
from app.main import app
from app.models.account import Account
from app.models.profile import Profile
from app.services import credit_service, stripe_service
from app.services.model_router import route

settings = get_settings()
TEST_URL = settings.database_url.rsplit("/", 1)[0] + "/matchforge_test"

engine = create_engine(TEST_URL)
TestSession = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture()
def db():
    session = TestSession()
    yield session
    session.close()


@pytest.fixture()
def billing_on():
    prior = settings.billing_enabled
    settings.billing_enabled = True
    yield
    settings.billing_enabled = prior


def _signup_and_login(client: TestClient) -> str:
    """Run the real magic-link flow; returns the account email."""
    email = f"it-{uuid.uuid4().hex[:10]}@test.local"
    resp = client.post("/signup", data={"email": email})
    assert resp.status_code == 200
    match = re.search(r'href="[^"]*(/auth/verify\?[^"]+)"', resp.text)
    if not match:
        pytest.skip("SMTP configured — dev magic link not exposed")
    verify = client.get(match.group(1).replace("&amp;", "&"), follow_redirects=False)
    assert verify.status_code in (302, 303)
    return email


def _account_id(db, email: str) -> int:
    return db.query(Account).filter(Account.email == email).one().id


def _make_profile(db, account_id: int | None, name="Sarah") -> int:
    profile = Profile(account_id=account_id, name=name, platform="tinder")
    db.add(profile)
    db.commit()
    return profile.id


def test_signup_verify_session_flow(db):
    client = TestClient(app)
    email = _signup_and_login(client)
    account = db.query(Account).filter(Account.email == email).one()
    assert account.email_verified_at is not None
    # session is live: dashboard gates on legal/onboarding, NOT back to login
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" not in resp.headers["location"]
    # signup grant landed
    assert credit_service._raw_balance(db, account.id) == settings.signup_grant_tokens


def test_profile_endpoints_enforce_ownership(db):
    owner, intruder = TestClient(app), TestClient(app)
    owner_email = _signup_and_login(owner)
    _signup_and_login(intruder)
    profile_id = _make_profile(db, _account_id(db, owner_email))

    # intruder can neither read, rename, nor delete
    assert intruder.get(f"/profiles/{profile_id}").status_code in (403, 404)
    assert (
        intruder.patch(
            f"/profiles/{profile_id}", json={"display_name": "hax"}
        ).status_code
        in (403, 404)
    )
    assert intruder.delete(f"/profiles/{profile_id}").status_code in (403, 404)
    assert (
        intruder.get(f"/dashboard/cards/{profile_id}").status_code == 404
    )

    # owner renames fine, and the response echoes it
    resp = owner.patch(f"/profiles/{profile_id}", json={"display_name": "Coffee Sarah"})
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Coffee Sarah"

    # legacy NULL-account rows are not readable by anyone
    orphan_id = _make_profile(db, None)
    assert owner.get(f"/profiles/{orphan_id}").status_code in (403, 404)


def test_free_note_charges_nothing(db, billing_on):
    client = TestClient(app)
    email = _signup_and_login(client)
    account_id = _account_id(db, email)
    profile_id = _make_profile(db, account_id)
    before = credit_service._raw_balance(db, account_id)

    resp = client.post(
        f"/profiles/{profile_id}/evidence/note",
        data={"note": "met at the gym, seems genuine", "rerank": "false"},
    )
    assert resp.status_code == 200
    db.expire_all()
    assert credit_service._raw_balance(db, account_id) == before


def test_concurrent_charges_cannot_double_spend(db, billing_on):
    """10 racing charges against a balance that affords exactly 5."""
    account = Account(email=f"race-{uuid.uuid4().hex[:8]}@test.local")
    db.add(account)
    db.commit()
    cost = route("profile_screenshot").token_cost
    credit_service.grant_tokens(db, account.id, cost * 5, "test_seed")
    db.commit()

    results: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(10)

    def worker():
        session = TestSession()
        barrier.wait()
        try:
            credit_service.charge_tokens(session, account.id, "profile_screenshot")
            session.commit()
            outcome = "ok"
        except HTTPException as exc:
            session.rollback()
            outcome = f"http{exc.status_code}"
        finally:
            session.close()
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count("ok") == 5, results
    assert results.count("http402") == 5, results
    db.expire_all()
    assert credit_service._raw_balance(db, account.id) == 0


def test_stripe_credit_is_idempotent(db, billing_on):
    account = Account(email=f"stripe-{uuid.uuid4().hex[:8]}@test.local")
    db.add(account)
    db.commit()
    ref = f"cs_test_{uuid.uuid4().hex[:12]}"

    first = stripe_service.credit_purchase(
        db, account_id=account.id, tokens=200, stripe_ref=ref,
        topup_usd=10, kind="checkout",
    )
    assert first is not None
    second = stripe_service.credit_purchase(
        db, account_id=account.id, tokens=200, stripe_ref=ref,
        topup_usd=10, kind="webhook",
    )
    assert second is None
    db.expire_all()
    assert credit_service._raw_balance(db, account.id) == 200


def test_rate_limiter_trips_and_recovers():
    from app.core import ratelimit

    req = SimpleNamespace(headers={}, client=SimpleNamespace(host="203.0.113.9"))
    scope = f"test-{uuid.uuid4().hex[:6]}"
    ratelimit.enforce(req, scope=scope, limit=2, window_seconds=60)
    ratelimit.enforce(req, scope=scope, limit=2, window_seconds=60)
    with pytest.raises(HTTPException) as exc_info:
        ratelimit.enforce(req, scope=scope, limit=2, window_seconds=60)
    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers
    # a different identity is unaffected
    ratelimit.enforce(
        req, scope=scope, limit=2, window_seconds=60, identity="someone-else"
    )
