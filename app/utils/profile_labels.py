"""User-facing labels for profile settings and dashboard."""

GOAL_LABELS = {
    "ltr": "Long-term relationship",
    "marriage": "Marriage",
    "casual": "Casual dating",
    "hookups": "Short-term / Hookups",
    "friendship": "Friendship",
    "undecided": "Undecided",
    "other": "Other",
}

GENDER_LABELS = {"male": "Male", "female": "Female"}

SEEKING_LABELS = {"male": "men", "female": "women"}


def effective_preferred_genders(
    gender: str | None, preferred_genders: list[str] | None
) -> list[str]:
    if preferred_genders:
        return preferred_genders
    if gender == "male":
        return ["female"]
    if gender == "female":
        return ["male"]
    return ["male", "female"]


def format_seeking(preferred_genders: list[str]) -> str:
    if set(preferred_genders) == {"male", "female"}:
        return "men & women"
    if "female" in preferred_genders:
        return "women"
    if "male" in preferred_genders:
        return "men"
    return "matches"


def format_goals(goals: list[str]) -> str:
    if not goals:
        return "No goals set"
    return ", ".join(GOAL_LABELS.get(g, g.replace("_", " ").title()) for g in goals)


def format_user_badge(
    *,
    gender: str | None,
    preferred_genders: list[str] | None,
    goals: list[str] | None,
) -> str:
    parts: list[str] = []
    if gender:
        parts.append(GENDER_LABELS.get(gender, gender.replace("_", " ").title()))
    seeking = effective_preferred_genders(gender, preferred_genders)
    parts.append(f"Seeking {format_seeking(seeking)}")
    if goals:
        parts.append(format_goals(goals))
    return " · ".join(parts)


def match_profile_label(
    *,
    gender: str | None,
    preferred_genders: list[str] | None,
    goals: list[str] | None,
) -> str:
    seeking = format_seeking(effective_preferred_genders(gender, preferred_genders))
    goal_part = format_goals(goals or [])
    return f"Seeking {seeking} · {goal_part}"