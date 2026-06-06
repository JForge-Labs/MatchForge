"""Pydantic schemas for user onboarding."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.profile import PreferenceVectorOut

Gender = Literal["male", "female", "non_binary", "prefer_not_to_say"]
Intention = Literal[
    "ltr",
    "marriage",
    "casual",
    "hookups",
    "friendship",
    "undecided",
    "other",
]


class OnboardingStatus(BaseModel):
    onboarding_complete: bool
    gender: str | None = None
    intentions: list[str] = Field(default_factory=list)
    has_preference_vector: bool = False
    preference_vector: PreferenceVectorOut | None = None


class OnboardingProfileIn(BaseModel):
    gender: Gender
    intentions: list[Intention] = Field(..., min_length=1)
    other_intention_note: str | None = None


class OnboardingProfileOut(BaseModel):
    onboarding_complete: bool
    gender: str
    intentions: list[str]
    preference_vector: PreferenceVectorOut
    ui_context: dict = Field(default_factory=dict)
    example_count: int = 0
    message: str

    model_config = {"from_attributes": True}


class UserProfileOut(BaseModel):
    id: int
    gender: str | None = None
    intentions: list = Field(default_factory=list)
    onboarding_complete: bool
    ui_context: dict = Field(default_factory=dict)
    preference_vector: PreferenceVectorOut | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}