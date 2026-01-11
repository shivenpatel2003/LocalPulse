"""
Application Settings

Pydantic-based settings management with environment variable support.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Supabase Configuration
    supabase_url: str
    supabase_key: str

    # AI Provider Keys
    anthropic_api_key: str
    openai_api_key: str | None = None

    # External Data Sources
    google_places_api_key: str | None = None

    # Application Settings
    environment: Literal["development", "staging", "production"] = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Agent Configuration
    max_collector_agents: int = 5
    analysis_model: str = "claude-3-5-sonnet-20241022"
    embedding_model: str = "text-embedding-3-small"

    # Memory Configuration
    short_term_memory_ttl: int = 3600  # 1 hour in seconds
    episodic_memory_retention_days: int = 30

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()
