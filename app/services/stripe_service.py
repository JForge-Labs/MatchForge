"""Stripe Checkout and webhook handling for dynamic token top-ups."""
import logging

import stripe
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.account import Account
from app.models.credits import CreditTransaction
from app.services import credit_service

logger = logging.getLogger(__name__)
settings = get_settings()


def stripe_configured() -> bool:
    return bool(
        settings.stripe_secret_key
        and settings.stripe_publishable_key
        and settings.stripe_product_id
    )


def _client() -> None:
    if not settings.stripe_secret_key:
        raise HTTPException(503, "Stripe is not configured")
    stripe.api_key = settings.stripe_secret_key


def dollars_to_tokens(amount_usd: int) -> int:
    return amount_usd * settings.tokens_per_usd


def validate_topup_amount(amount_usd: int) -> int:
    amount = int(amount_usd)
    if amount < settings.min_topup_usd:
        raise HTTPException(
            400,
            detail={
                "error": "topup_below_minimum",
                "min_usd": settings.min_topup_usd,
            },
        )
    if amount > 500:
        raise HTTPException(400, detail={"error": "topup_above_maximum", "max_usd": 500})
    return amount


def purchase_already_credited(db: Session, stripe_ref: str) -> bool:
    row = (
        db.query(CreditTransaction)
        .filter(
            CreditTransaction.reason == "stripe_purchase",
            CreditTransaction.metadata_json["stripe_ref"].astext == stripe_ref,
        )
        .first()
    )
    return row is not None


def credit_purchase(
    db: Session,
    *,
    account_id: int,
    tokens: int,
    stripe_ref: str,
    topup_usd: int,
    kind: str,
) -> int | None:
    if tokens <= 0 or purchase_already_credited(db, stripe_ref):
        return None
    balance = credit_service.grant_tokens(
        db,
        account_id,
        tokens,
        "stripe_purchase",
        note=f"Stripe {kind}: ${topup_usd}",
        metadata={
            "stripe_ref": stripe_ref,
            "topup_usd": topup_usd,
            "kind": kind,
        },
    )
    db.commit()
    logger.info(
        "Credited %s tokens to account %s via Stripe %s (%s)",
        tokens,
        account_id,
        kind,
        stripe_ref,
    )
    return balance


def create_checkout_session(db: Session, account: Account, amount_usd: int) -> dict:
    if not stripe_configured():
        raise HTTPException(503, "Stripe is not configured")
    if not credit_service.billing_enabled():
        raise HTTPException(503, "Billing is not enabled yet")

    amount_usd = validate_topup_amount(amount_usd)
    tokens = dollars_to_tokens(amount_usd)
    _client()

    base = settings.app_url.rstrip("/")
    session = stripe.checkout.Session.create(
        mode="payment",
        customer_email=account.email,
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product": settings.stripe_product_id,
                    "unit_amount": amount_usd * 100,
                },
                "quantity": 1,
            }
        ],
        metadata={
            "account_id": str(account.id),
            "tokens": str(tokens),
            "topup_usd": str(amount_usd),
            "kind": "manual_topup",
        },
        success_url=f"{base}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base}/billing/cancel",
    )
    return {
        "checkout_url": session.url,
        "session_id": session.id,
        "amount_usd": amount_usd,
        "tokens": tokens,
    }


def handle_webhook(db: Session, payload: bytes, signature: str | None) -> dict:
    if not settings.stripe_webhook_secret:
        raise HTTPException(503, "Stripe webhook secret is not configured")
    _client()

    try:
        event = stripe.Webhook.construct_event(
            payload, signature, settings.stripe_webhook_secret
        )
    except ValueError:
        raise HTTPException(400, "Invalid webhook payload") from None
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid webhook signature") from None

    etype = event["type"]
    data = event["data"]["object"]

    if etype == "checkout.session.completed":
        _handle_checkout_completed(db, data)
    elif etype == "payment_intent.succeeded":
        _handle_payment_intent_succeeded(db, data)
    elif etype == "payment_intent.payment_failed":
        logger.warning("Stripe payment failed: %s", data.get("id"))

    return {"received": True, "type": etype}


def _parse_metadata(meta: dict) -> tuple[int, int, int, str] | None:
    try:
        account_id = int(meta["account_id"])
        tokens = int(meta["tokens"])
        topup_usd = int(meta.get("topup_usd") or 0)
        kind = str(meta.get("kind") or "topup")
    except (KeyError, TypeError, ValueError):
        return None
    return account_id, tokens, topup_usd, kind


def _handle_checkout_completed(db: Session, session: dict) -> None:
    if session.get("payment_status") != "paid":
        return
    meta = session.get("metadata") or {}
    parsed = _parse_metadata(meta)
    if not parsed:
        logger.warning("Checkout session missing metadata: %s", session.get("id"))
        return
    account_id, tokens, topup_usd, kind = parsed
    credit_purchase(
        db,
        account_id=account_id,
        tokens=tokens,
        stripe_ref=session["id"],
        topup_usd=topup_usd,
        kind=kind,
    )


def _handle_payment_intent_succeeded(db: Session, intent: dict) -> None:
    meta = intent.get("metadata") or {}
    if meta.get("kind") != "auto_topup":
        return
    parsed = _parse_metadata(meta)
    if not parsed:
        logger.warning("PaymentIntent missing metadata: %s", intent.get("id"))
        return
    account_id, tokens, topup_usd, kind = parsed
    credit_purchase(
        db,
        account_id=account_id,
        tokens=tokens,
        stripe_ref=intent["id"],
        topup_usd=topup_usd,
        kind=kind,
    )