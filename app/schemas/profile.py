"""Pydantic schemas for profiles, rankings, and toolbox operations."""
from datetime import datetime

from pydantic import BaseModel, Field


class PreferenceVectorOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    traits: dict
    weights: dict
    is_default: bool

    model_config = {"from_attributes": True}


class SocialEnrichmentOut(BaseModel):
    id: int
    platform: str
    username: str | None = None
    url: str | None = None
    summary: str | None = None
    findings: dict = Field(default_factory=dict)
    enriched_at: datetime

    model_config = {"from_attributes": True}


class TrustScoresOut(BaseModel):
    authenticity_score: float | None = None
    naturalness_score: float | None = None
    catfish_risk_score: float | None = None
    bot_risk_score: float | None = None
    overall_trust_score: float | None = None
    catfish_flag: str | None = None
    catfish_flag_label: str | None = None
    trust_explanation: str | None = None
    trust_badge: str | None = None
    catfish_badge: str | None = None
    bot_badge: str | None = None
    risk_factors: list[str] = Field(default_factory=list)


class ProfileOut(BaseModel):
    id: int
    name: str | None = None
    username: str | None = None
    bio: str | None = None
    age: int | None = None
    location: str | None = None
    platform: str | None = None
    photos: list = Field(default_factory=list)
    extracted_data: dict = Field(default_factory=dict)
    vision_analysis: dict = Field(default_factory=dict)
    attractiveness_score: float | None = None
    compatibility_score: float | None = None
    red_flag_score: float | None = None
    overall_score: float | None = None
    authenticity_score: float | None = None
    naturalness_score: float | None = None
    catfish_risk_score: float | None = None
    bot_risk_score: float | None = None
    trust_analysis: dict = Field(default_factory=dict)
    enrichment_status: str = "pending"
    status: str = "new"
    created_at: datetime
    social_enrichments: list[SocialEnrichmentOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class RankingOut(BaseModel):
    id: int
    profile_id: int
    overall_score: float
    compatibility_score: float
    attractiveness_score: float
    red_flag_score: float
    authenticity_score: float | None = None
    naturalness_score: float | None = None
    catfish_risk_score: float | None = None
    bot_risk_score: float | None = None
    trust_explanation: str | None = None
    explanation: str | None = None
    percolation_priority: float
    user_override_rank: int | None = None
    feedback: str | None = None
    profile: ProfileOut

    model_config = {"from_attributes": True}


class UploadResult(BaseModel):
    profiles_created: int
    profiles_merged: int = 0
    profiles: list[ProfileOut]
    trust_breakdown: list[TrustScoresOut] = Field(default_factory=list)
    message: str


class EnrichRequest(BaseModel):
    profile_ids: list[int] = Field(default_factory=list)
    platforms: list[str] = Field(
        default_factory=lambda: ["facebook", "instagram", "linkedin", "x"]
    )


class EnrichResult(BaseModel):
    profile_id: int
    enrichments: list[SocialEnrichmentOut]
    status: str


class FeedbackRequest(BaseModel):
    ranking_id: int
    feedback: str = Field(..., pattern="^(like|dislike|skip|superlike)$")


class PercolatedDashboard(BaseModel):
    total_profiles: int
    shortlist: list[RankingOut]
    preference_vector: PreferenceVectorOut | None = None
    user_gender: str | None = None
    user_intentions: list[str] = Field(default_factory=list)
    onboarding_complete: bool = False


class ShareOut(BaseModel):
    ranking_id: int
    profile_id: int
    share_token: str
    share_url: str
    referral_url: str
    text: str
    title: str