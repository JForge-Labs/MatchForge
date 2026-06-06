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

    # AI backends (local-first)
    ollama_base_url: str = "http://localhost:11434"
    lmstudio_base_url: str = "http://localhost:1234/v1"
    embedding_model: str = "nomic-embed-text"
    vision_model: str = "llava"
    text_model: str = "llama3.2"


@lru_cache
def get_settings() -> Settings:
    return Settings()
