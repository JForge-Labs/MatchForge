"""User profile model for onboarding and personalization."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), unique=True, nullable=True
    )
    gender: Mapped[str | None] = mapped_column(String(32))
    preferred_genders: Mapped[list] = mapped_column(JSONB, default=list)
    intentions: Mapped[list] = mapped_column(JSONB, default=list)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    preference_vector_id: Mapped[int | None] = mapped_column(
        ForeignKey("preference_vectors.id"), nullable=True
    )
    example_analyses: Mapped[list] = mapped_column(JSONB, default=list)
    ui_context: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    account = relationship("Account", back_populates="profile")
    preference_vector = relationship("PreferenceVector", foreign_keys=[preference_vector_id])