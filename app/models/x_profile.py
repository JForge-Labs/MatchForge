"""Cache of public X (Twitter) profile data fetched via the official X API v2."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class XProfileCache(Base):
    """TTL cache so repeat verifications don't re-bill X API post reads."""

    __tablename__ = "x_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    x_user_id: Mapped[str | None] = mapped_column(String(32))
    user_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    timeline: Mapped[list] = mapped_column(JSONB, default=list)
    signals: Mapped[dict] = mapped_column(JSONB, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
