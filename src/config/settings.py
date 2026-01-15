"""
Application Settings.

Centralized configuration using Pydantic Settings with environment variable loading.
All settings are validated at startup - missing required values will raise an error.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Supabase
    # -------------------------------------------------------------------------
    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_key: SecretStr = Field(..., description="Supabase anon or service key")

    # -------------------------------------------------------------------------
    # Neo4j (Knowledge Graph)
    # -------------------------------------------------------------------------
    neo4j_uri: str = Field(..., description="Neo4j connection URI (bolt://)")
    neo4j_user: str = Field(..., description="Neo4j username")
    neo4j_password: SecretStr = Field(..., description="Neo4j password")

    # -------------------------------------------------------------------------
    # Pinecone (Vector Store)
    # -------------------------------------------------------------------------
    pinecone_api_key: SecretStr = Field(..., description="Pinecone API key")
    pinecone_index_name: str = Field(
        default="localpulse-reviews",
        description="Pinecone index name",
    )

    # -------------------------------------------------------------------------
    # OpenAI (Embeddings)
    # -------------------------------------------------------------------------
    openai_api_key: SecretStr = Field(..., description="OpenAI API key for embeddings")

    # -------------------------------------------------------------------------
    # Anthropic (Claude LLM)
    # -------------------------------------------------------------------------
    anthropic_api_key: SecretStr | None = Field(
        default=None, description="Anthropic API key for Claude"
    )

    # -------------------------------------------------------------------------
    # Cohere (Reranking)
    # -------------------------------------------------------------------------
    cohere_api_key: SecretStr = Field(..., description="Cohere API key for reranking")

    # -------------------------------------------------------------------------
    # Google (Places API)
    # -------------------------------------------------------------------------
    google_places_api_key: SecretStr | None = Field(
        default=None, description="Google Places API key"
    )

    # -------------------------------------------------------------------------
    # Redis (Caching / Working Memory)
    # -------------------------------------------------------------------------
    redis_url: str | None = Field(default=None, description="Redis connection URL")

    # -------------------------------------------------------------------------
    # SendGrid (Email Delivery)
    # -------------------------------------------------------------------------
    sendgrid_api_key: SecretStr = Field(..., description="SendGrid API key for emails")
    from_email: str = Field(
        default="reports@localpulse.io",
        description="Sender email address for outgoing emails",
    )
    from_name: str = Field(
        default="LocalPulse",
        description="Sender display name for outgoing emails",
    )
    reply_to_email: str = Field(
        default="support@localpulse.io",
        description="Reply-to email address",
    )

    # -------------------------------------------------------------------------
    # Application Settings
    # -------------------------------------------------------------------------
    app_env: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Application environment",
    )
    debug: bool = Field(
        default=True,
        description="Enable debug mode",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are only loaded once.
    Call get_settings.cache_clear() to reload settings if needed.
    """
    return Settings()


# Convenience export for direct import
settings = get_settings()
