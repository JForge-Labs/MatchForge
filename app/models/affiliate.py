"""Affiliate partners and commission ledger."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Affiliate(Base):
    __tablename__ = "affiliates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    link_code: Mapped[str | None] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    contact_email: Mapped[str] = mapped_column(String(320))
    commission_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), default=Decimal("0.15")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    commissions = relationship(
        "AffiliateCommission",
        back_populates="affiliate",
        cascade="all, delete-orphan",
    )
    referred_accounts = relationship(
        "Account",
        foreign_keys="Account.referred_by_affiliate_id",
        back_populates="referred_by_affiliate",
    )


class AffiliateCommission(Base):
    __tablename__ = "affiliate_commissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    affiliate_id: Mapped[int] = mapped_column(
        ForeignKey("affiliates.id", ondelete="CASCADE"), index=True
    )
    referred_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    stripe_ref: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    gross_cents: Mapped[int] = mapped_column(Integer)
    commission_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payout_note: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    affiliate = relationship("Affiliate", back_populates="commissions")
    referred_account = relationship(
        "Account",
        foreign_keys=[referred_account_id],
        back_populates="affiliate_commissions",
    )
