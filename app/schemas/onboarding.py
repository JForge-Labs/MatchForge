"""Pydantic schemas for user onboarding."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.profile import PreferenceVectorOut

Gender = Literal["male", "female"]
PreferredGender = Literal["male", "female"]
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
    policies_accepted: bool = False
    policies_version: str | None = None
    onboarding_complete: bool
    gender: str | None = None
    display_name: str | None = None
    age: int | None = None
    location: str | None = None
    bio: str | None = None
    has_profile_photo: bool = False
    preferred_genders: list[str] = Field(default_factory=list)
    intentions: list[str] = Field(default_factory=list)
    has_preference_vector: bool = False
    preference_vector: PreferenceVectorOut | None = None


class OnboardingProfileIn(BaseModel):
    gender: Gender
    preferred_genders: list[PreferredGender] = Field(..., min_length=1)
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