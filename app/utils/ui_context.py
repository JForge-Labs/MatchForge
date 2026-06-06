"""Shared branding and environment context for HTML templates."""
from app.core.config import get_settings

_ENV_UI = {
    "development": {
        "label": "Development",
        "short": "Dev",
        "class": "env-dev",
        "show_banner": True,
        "theme_color": "#5b4cdb",
    },
    "staging": {
        "label": "Staging",
        "short": "Stage",
        "class": "env-stage",
        "show_banner": True,
        "theme_color": "#d97706",
    },
    "production": {
        "label": "Production",
        "short": "Prod",
        "class": "env-prod",
        "show_banner": False,
        "theme_color": "#7c6cf0",
    },
}


def env_ui(app_env: str) -> dict:
    """Map APP_ENV to banner label, CSS class, and theme color."""
    key = (app_env or "development").lower()
    return _ENV_UI.get(key, _ENV_UI["development"])


def ui_context(*, authed: bool | None = None, active: str | None = None, **extra) -> dict:
    """Base template variables for consistent premium chrome across pages."""
    settings = get_settings()
    env = env_ui(settings.app_env)
    return {
        "app_name": settings.app_name,
        "app_env": settings.app_env,
        "app_domain": settings.app_domain,
        "app_url": settings.app_url.rstrip("/"),
        "env_label": env["label"],
        "env_short": env["short"],
        "env_class": env["class"],
        "show_env_banner": env["show_banner"],
        "theme_color": env["theme_color"],
        "authed": authed,
        "active": active,
        **extra,
    }