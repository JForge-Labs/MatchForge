"""Map user activities to Grok models and internal token costs."""
from dataclasses import dataclass

from app.core.config import get_settings

settings = get_settings()


@dataclass(frozen=True)
class LlmRoute:
    activity: str
    model: str
    token_cost: int
    description: str


ACTIVITIES: dict[str, LlmRoute] = {
    "profile_screenshot": LlmRoute(
        "profile_screenshot",
        settings.xai_vision_model,
        12,
        "Initial profile screenshot extract + trust photos",
    ),
    "message_screenshot": LlmRoute(
        "message_screenshot",
        settings.xai_vision_model,
        8,
        "Chat/message screenshot added to existing profile",
    ),
    "user_note": LlmRoute(
        "user_note",
        settings.xai_text_fast,
        3,
        "Free-text note structured and merged into profile",
    ),
    "profile_agent": LlmRoute(
        "profile_agent",
        settings.xai_text_fast,
        5,
        "Agent prompt interpretation and profile merge",
    ),
    "profile_agent_image": LlmRoute(
        "profile_agent_image",
        settings.xai_vision_model,
        10,
        "Additional profile screenshot via agent (multi-platform enrich)",
    ),
    "social_link": LlmRoute(
        "social_link",
        settings.xai_text_fast,
        5,
        "Social profile URL dropped into agent compose",
    ),
    "rank_refresh": LlmRoute(
        "rank_refresh",
        settings.xai_text_fast,
        5,
        "Re-score profile after new evidence",
    ),
    "deep_vet": LlmRoute(
        "deep_vet",
        settings.xai_text_reason,
        25,
        "Deep vetting synthesis",
    ),
    "onboarding_example": LlmRoute(
        "onboarding_example",
        settings.xai_vision_model,
        5,
        "Onboarding liked-profile example",
    ),
    "onboarding_pref": LlmRoute(
        "onboarding_pref",
        settings.xai_text_fast,
        8,
        "Preference vector generation",
    ),
}

FOUNDER_CAP = 50


def route(activity: str) -> LlmRoute:
    if activity not in ACTIVITIES:
        raise ValueError(f"Unknown LLM activity: {activity}")
    return ACTIVITIES[activity]