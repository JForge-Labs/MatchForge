"""Affiliate partner attribution and commission ledger."""
import logging
import re
import secrets
from datetime import datetime, timezone
from decimal import Decimal

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.account import Account
from app.models.affiliate import Affiliate, AffiliateCommission

logger = logging.getLogger(__name__)
settings = get_settings()

AFFILIATE_COOKIE = "mf_aff"
AFFILIATE_COOKIE_MAX_AGE = 30 * 24 * 3600
PARTNER_TOKEN_MAX_AGE = 30 * 24 * 3600
PARTNER_TOKEN_SALT = "matchforge-partner-dashboard"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
TEST_SLUG_RE = re.compile(r"^aff-[a-f0-9]{6}$")


def affiliates_enabled() -> bool:
    return settings.affiliates_enabled


def build_affiliate_url(link_code: str) -> str:
    base = settings.app_url.rstrip("/")
    return f"{base}/join/{link_code}"


def _partner_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=PARTNER_TOKEN_SALT)


def build_partner_dashboard_url(affiliate_id: int) -> str:
    token = _partner_serializer().dumps({"affiliate_id": affiliate_id})
    base = settings.app_url.rstrip("/")
    return f"{base}/partner?token={token}"


def resolve_partner_token(token: str) -> int | None:
    if not token or not token.strip():
        return None
    try:
        data = _partner_serializer().loads(token.strip(), max_age=PARTNER_TOKEN_MAX_AGE)
        return int(data["affiliate_id"])
    except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError):
        return None


def get_affiliate_by_id(db: Session, affiliate_id: int) -> Affiliate | None:
    return db.query(Affiliate).filter(Affiliate.id == affiliate_id).first()


def is_test_affiliate(affiliate: Affiliate) -> bool:
    if affiliate.contact_email.endswith("@affiliate-test.local"):
        return True
    if affiliate.name == "Test Partner" and TEST_SLUG_RE.match(affiliate.slug):
        return True
    return False


def count_test_affiliates(db: Session) -> int:
    return sum(1 for a in db.query(Affiliate).all() if is_test_affiliate(a))


def delete_test_affiliates(db: Session) -> int:
    rows = [a for a in db.query(Affiliate).all() if is_test_affiliate(a)]
    for row in rows:
        db.delete(row)
    db.flush()
    return len(rows)


def normalize_slug(slug: str) -> str:
    return slug.strip().lower()


def is_valid_slug(slug: str) -> bool:
    return bool(SLUG_RE.match(normalize_slug(slug)))


def get_affiliate_by_slug(db: Session, slug: str) -> Affiliate | None:
    if not slug or not slug.strip():
        return None
    return (
        db.query(Affiliate)
        .filter(Affiliate.slug == normalize_slug(slug), Affiliate.is_active.is_(True))
        .first()
    )


def ensure_link_code(db: Session, affiliate: Affiliate) -> str:
    if affiliate.link_code:
        return affiliate.link_code
    for _ in range(12):
        code = secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:10]
        taken = (
            db.query(Affiliate.id)
            .filter(Affiliate.link_code == code)
            .first()
        )
        if not taken:
            affiliate.link_code = code
            db.flush()
            return code
    raise RuntimeError("Could not allocate affiliate link code")


def get_affiliate_by_ref(db: Session, ref: str) -> Affiliate | None:
    """Resolve an affiliate by opaque link code (preferred) or legacy slug."""
    if not ref or not ref.strip():
        return None
    token = ref.strip()
    row = (
        db.query(Affiliate)
        .filter(Affiliate.link_code == token, Affiliate.is_active.is_(True))
        .first()
    )
    if row:
        return row
    return get_affiliate_by_slug(db, token)


def resolve_affiliate(
    db: Session, affiliate_ref: str | None, signup_email: str
) -> Affiliate | None:
    if not affiliates_enabled() or not affiliate_ref or not affiliate_ref.strip():
        return None
    affiliate = get_affiliate_by_ref(db, affiliate_ref)
    if not affiliate:
        return None
    if affiliate.contact_email.lower() == signup_email.strip().lower():
        return None
    return affiliate


def affiliate_join_ref(db: Session, affiliate: Affiliate) -> str:
    return ensure_link_code(db, affiliate)


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    visible = local[:1] if local else ""
    return f"{visible}***@{domain}"


def record_commission(
    db: Session,
    *,
    account_id: int,
    stripe_ref: str,
    topup_usd: int,
) -> AffiliateCommission | None:
    if not affiliates_enabled() or topup_usd <= 0:
        return None

    existing = (
        db.query(AffiliateCommission)
        .filter(AffiliateCommission.stripe_ref == stripe_ref)
        .first()
    )
    if existing:
        return existing

    account = db.query(Account).filter(Account.id == account_id).first()
    if not account or not account.referred_by_affiliate_id:
        return None

    affiliate = (
        db.query(Affiliate)
        .filter(
            Affiliate.id == account.referred_by_affiliate_id,
            Affiliate.is_active.is_(True),
        )
        .first()
    )
    if not affiliate:
        return None

    gross_cents = topup_usd * 100
    rate = Decimal(str(affiliate.commission_rate))
    commission_cents = int(round(gross_cents * rate))

    row = AffiliateCommission(
        affiliate_id=affiliate.id,
        referred_account_id=account_id,
        stripe_ref=stripe_ref,
        gross_cents=gross_cents,
        commission_cents=commission_cents,
        status="pending",
    )
    db.add(row)
    db.flush()
    logger.info(
        "Affiliate commission: affiliate=%s account=%s gross_cents=%s commission_cents=%s ref=%s",
        affiliate.id,
        account_id,
        gross_cents,
        commission_cents,
        stripe_ref,
    )
    return row


def _commission_sums(db: Session, affiliate_id: int) -> dict:
    pending = (
        db.query(func.coalesce(func.sum(AffiliateCommission.commission_cents), 0))
        .filter(
            AffiliateCommission.affiliate_id == affiliate_id,
            AffiliateCommission.status == "pending",
        )
        .scalar()
    ) or 0
    paid = (
        db.query(func.coalesce(func.sum(AffiliateCommission.commission_cents), 0))
        .filter(
            AffiliateCommission.affiliate_id == affiliate_id,
            AffiliateCommission.status == "paid",
        )
        .scalar()
    ) or 0
    revenue = (
        db.query(func.coalesce(func.sum(AffiliateCommission.gross_cents), 0))
        .filter(AffiliateCommission.affiliate_id == affiliate_id)
        .scalar()
    ) or 0
    return {
        "pending_commission_cents": int(pending),
        "paid_commission_cents": int(paid),
        "referred_revenue_cents": int(revenue),
    }


def affiliate_signup_counts(db: Session, affiliate_id: int) -> dict:
    total = (
        db.query(func.count(Account.id))
        .filter(Account.referred_by_affiliate_id == affiliate_id)
        .scalar()
    ) or 0
    verified = (
        db.query(func.count(Account.id))
        .filter(
            Account.referred_by_affiliate_id == affiliate_id,
            Account.email_verified_at.isnot(None),
        )
        .scalar()
    ) or 0
    return {"signups_total": int(total), "signups_verified": int(verified)}


def affiliate_stats(db: Session, affiliate: Affiliate) -> dict:
    counts = affiliate_signup_counts(db, affiliate.id)
    sums = _commission_sums(db, affiliate.id)
    rate = float(affiliate.commission_rate)
    link_code = ensure_link_code(db, affiliate)
    return {
        "id": affiliate.id,
        "slug": affiliate.slug,
        "name": affiliate.name,
        "contact_email": affiliate.contact_email,
        "commission_rate": rate,
        "commission_rate_pct": round(rate * 100, 2),
        "is_active": affiliate.is_active,
        "notes": affiliate.notes,
        "link_code": link_code,
        "affiliate_url": build_affiliate_url(link_code),
        "partner_dashboard_url": build_partner_dashboard_url(affiliate.id),
        "created_at": affiliate.created_at.isoformat() if affiliate.created_at else None,
        **counts,
        **sums,
    }


def list_affiliates_with_stats(
    db: Session, *, include_test: bool = True
) -> list[dict]:
    affiliates = db.query(Affiliate).order_by(Affiliate.created_at.desc()).all()
    if not include_test:
        affiliates = [a for a in affiliates if not is_test_affiliate(a)]
    return [affiliate_stats(db, a) for a in affiliates]


def list_commissions(
    db: Session,
    *,
    affiliate_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    q = (
        db.query(AffiliateCommission, Account.email)
        .join(Account, Account.id == AffiliateCommission.referred_account_id)
        .order_by(AffiliateCommission.created_at.desc())
    )
    if affiliate_id is not None:
        q = q.filter(AffiliateCommission.affiliate_id == affiliate_id)
    if status:
        q = q.filter(AffiliateCommission.status == status)
    rows = q.limit(limit).all()
    return [
        {
            "id": comm.id,
            "affiliate_id": comm.affiliate_id,
            "referred_account_id": comm.referred_account_id,
            "referred_email_masked": mask_email(email),
            "stripe_ref": comm.stripe_ref,
            "gross_cents": comm.gross_cents,
            "commission_cents": comm.commission_cents,
            "status": comm.status,
            "paid_at": comm.paid_at.isoformat() if comm.paid_at else None,
            "payout_note": comm.payout_note,
            "created_at": comm.created_at.isoformat() if comm.created_at else None,
        }
        for comm, email in rows
    ]


def mark_commissions_paid(
    db: Session,
    commission_ids: list[int],
    *,
    payout_note: str | None = None,
) -> int:
    if not commission_ids:
        return 0
    now = datetime.now(timezone.utc)
    rows = (
        db.query(AffiliateCommission)
        .filter(
            AffiliateCommission.id.in_(commission_ids),
            AffiliateCommission.status == "pending",
        )
        .all()
    )
    for row in rows:
        row.status = "paid"
        row.paid_at = now
        if payout_note:
            row.payout_note = payout_note
    db.flush()
    return len(rows)


def create_affiliate(
    db: Session,
    *,
    slug: str,
    name: str,
    contact_email: str,
    commission_rate: Decimal | float = Decimal("0.15"),
    notes: str | None = None,
) -> Affiliate:
    normalized = normalize_slug(slug)
    if not is_valid_slug(normalized):
        raise ValueError(
            "Slug must be 2–63 characters: lowercase letters, numbers, and hyphens "
            "(e.g. partner-name)."
        )
    email = contact_email.strip().lower()
    if "@" not in email:
        raise ValueError("Enter a valid contact email.")
    rate = Decimal(str(commission_rate))
    if rate <= 0 or rate > 1:
        raise ValueError("Commission rate must be between 0 and 100%.")
    existing = db.query(Affiliate).filter(Affiliate.slug == normalized).first()
    if existing:
        raise ValueError(f"Slug '{normalized}' is already taken.")
    affiliate = Affiliate(
        slug=normalized,
        name=name.strip(),
        contact_email=email,
        commission_rate=rate,
        notes=notes.strip() if notes else None,
    )
    db.add(affiliate)
    db.flush()
    ensure_link_code(db, affiliate)
    return affiliate


def partner_dashboard_context(db: Session, affiliate: Affiliate) -> dict:
    stats = affiliate_stats(db, affiliate)
    commissions = list_commissions(db, affiliate_id=affiliate.id, limit=50)
    return {
        "affiliate": stats,
        "commissions": commissions,
    }
