"""Account and email verification tokens."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_founder: Mapped[bool] = mapped_column(Boolean, default=False)
    founder_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    referral_code: Mapped[str | None] = mapped_column(String(16), unique=True, index=True)
    referred_by_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )

    profile = relationship("UserProfile", back_populates="account", uselist=False)
    tokens = relationship("AuthToken", back_populates="account")
    credits = relationship("AccountCredit", back_populates="account", uselist=False)
    credit_transactions = relationship("CreditTransaction", back_populates="account")
    referrals_made = relationship(
        "Referral",
        foreign_keys="Referral.referrer_account_id",
        back_populates="referrer",
    )
    referral_received = relationship(
        "Referral",
        foreign_keys="Referral.referred_account_id",
        back_populates="referred",
        uselist=False,
    )


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    purpose: Mapped[str] = mapped_column(String(32))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    account = relationship("Account", back_populates="tokens")