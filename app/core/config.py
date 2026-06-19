"""Application settings, loaded from environment / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "MatchForge"
    app_env: str = "development"
    app_domain: str = "match-forge.com"
    secret_key: str = "dev-insecure-change-me"
    auth_password: str = ""
    app_url: str = "http://localhost:8000"

    # Email (SMTP) — required in production for signup verification
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "MatchForge <noreply@match-forge.com>"
    smtp_use_tls: bool = True

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "info"

    database_url: str = (
        "postgresql+psycopg2://matchforge:changeme@localhost:5432/matchforge_dev"
    )
    redis_url: str = "redis://localhost:6379/0"

    # Brave Search (optional — improves public social enrichment)
    brave_api_key: str = ""

    # xAI Grok (all environments)
    xai_api_key: str = ""
    xai_vision_model: str = "grok-4.3"
    xai_text_fast: str = "grok-4.20-0309-non-reasoning"
    xai_text_reason: str = "grok-4.20-0309-reasoning"

    # Affiliate partners — revenue-share attribution via ?aff= links
    affiliates_enabled: bool = True

    # Monetization — disable while iterating (no charges, no 402 walls)
    billing_enabled: bool = False
    signup_grant_tokens: int = 100
    seed_min_tokens: int = 0  # tops up existing accounts on init (0 = disabled)

    # Stripe — dynamic top-up (no fixed Price ID; amount set per checkout)
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_product_id: str = ""
    tokens_per_usd: int = 20
    min_topup_usd: int = 10
    default_topup_usd: int = 20

    # Comma-separated admin emails for /admin dashboard
    admin_emails: str = ""

    # Capacity / surge traffic (foundational — in-process until Redis queue ships)
    overload_mode: bool = False  # manual kill-switch: set OVERLOAD_MODE=true on DO
    capacity_max_concurrent_uploads: int = 1
    capacity_retry_after_seconds: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()
