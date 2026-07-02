"""ORM models for profiles, rankings, and preference vectors."""
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class PreferenceVector(Base):
    __tablename__ = "preference_vectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    traits: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    weights: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    embedding = mapped_column(Vector(768), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    rankings: Mapped[list["Ranking"]] = relationship(back_populates="preference_vector")


class ProfileEvidence(Base):
    __tablename__ = "profile_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text)
    media_path: Mapped[str | None] = mapped_column(String(512))
    extracted_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    tokens_charged: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    profile: Mapped["Profile"] = relationship(back_populates="evidence")


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str | None] = mapped_column(String(256))
    username: Mapped[str | None] = mapped_column(String(256))
    bio: Mapped[str | None] = mapped_column(Text)
    age: Mapped[int | None] = mapped_column(Integer)
    location: Mapped[str | None] = mapped_column(String(256))
    platform: Mapped[str | None] = mapped_column(String(64))
    photos: Mapped[list] = mapped_column(JSONB, default=list)
    extracted_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    vision_analysis: Mapped[dict] = mapped_column(JSONB, default=dict)
    attractiveness_score: Mapped[float | None] = mapped_column(Float)
    compatibility_score: Mapped[float | None] = mapped_column(Float)
    red_flag_score: Mapped[float | None] = mapped_column(Float)
    overall_score: Mapped[float | None] = mapped_column(Float)
    authenticity_score: Mapped[float | None] = mapped_column(Float)
    naturalness_score: Mapped[float | None] = mapped_column(Float)
    catfish_risk_score: Mapped[float | None] = mapped_column(Float)
    bot_risk_score: Mapped[float | None] = mapped_column(Float)
    x_social_proof_score: Mapped[float | None] = mapped_column(Float)
    x_verification: Mapped[dict] = mapped_column(JSONB, default=dict)
    trust_analysis: Mapped[dict] = mapped_column(JSONB, default=dict)
    embedding = mapped_column(Vector(768), nullable=True)
    enrichment_status: Mapped[str] = mapped_column(String(32), default="pending")
    status: Mapped[str] = mapped_column(String(32), default="new")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    rankings: Mapped[list["Ranking"]] = relationship(back_populates="profile")
    social_enrichments: Mapped[list["SocialEnrichment"]] = relationship(
        back_populates="profile"
    )
    evidence: Mapped[list["ProfileEvidence"]] = relationship(back_populates="profile")


class Ranking(Base):
    __tablename__ = "rankings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), nullable=False)
    preference_vector_id: Mapped[int] = mapped_column(
        ForeignKey("preference_vectors.id"), nullable=False
    )
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    compatibility_score: Mapped[float] = mapped_column(Float, default=0.0)
    attractiveness_score: Mapped[float] = mapped_column(Float, default=0.0)
    red_flag_score: Mapped[float] = mapped_column(Float, default=0.0)
    authenticity_score: Mapped[float | None] = mapped_column(Float)
    naturalness_score: Mapped[float | None] = mapped_column(Float)
    catfish_risk_score: Mapped[float | None] = mapped_column(Float)
    bot_risk_score: Mapped[float | None] = mapped_column(Float)
    x_social_proof_score: Mapped[float | None] = mapped_column(Float)
    trust_explanation: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    user_override_rank: Mapped[int | None] = mapped_column(Integer)
    percolation_priority: Mapped[float] = mapped_column(Float, default=0.0)
    feedback: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    profile: Mapped["Profile"] = relationship(back_populates="rankings")
    preference_vector: Mapped["PreferenceVector"] = relationship(
        back_populates="rankings"
    )


class SocialEnrichment(Base):
    __tablename__ = "social_enrichments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    username: Mapped[str | None] = mapped_column(String(256))
    url: Mapped[str | None] = mapped_column(String(512))
    summary: Mapped[str | None] = mapped_column(Text)
    findings: Mapped[dict] = mapped_column(JSONB, default=dict)
    enriched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    profile: Mapped["Profile"] = relationship(back_populates="social_enrichments")