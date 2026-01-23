"""
Application Settings.

Centralized configuration using Pydantic Settings with environment variable loading.
All settings are validated at startup - missing required values will raise an error.

Production Mode:
    When app_env="production", additional validations apply:
    - api_key_enabled must be True
    - debug must be False
    - cors_allowed_origins cannot be ["*"]
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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
    # Cohere (Reranking & Embeddings)
    # -------------------------------------------------------------------------
    cohere_api_key: SecretStr = Field(..., description="Cohere API key for reranking and embeddings")
    cohere_embedding_model: str = Field(
        default="embed-english-v3.0",
        description="Cohere embedding model (e.g., embed-english-v3.0, embed-multilingual-v3.0)",
    )
    cohere_embedding_dimension: int = Field(
        default=1024,
        description="Embedding dimension (384, 512, 768, or 1024)",
    )

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

    # -------------------------------------------------------------------------
    # Security Settings
    # -------------------------------------------------------------------------
    api_key: SecretStr | None = Field(
        default=None,
        description="API key for authentication. If set, all requests require X-API-Key header.",
    )
    api_key_enabled: bool = Field(
        default=False,
        description="Enable API key authentication. Set True for production.",
    )

    # -------------------------------------------------------------------------
    # CORS Settings
    # -------------------------------------------------------------------------
    cors_allowed_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origins. Use ['*'] for development only.",
    )
    cors_allow_credentials: bool = Field(
        default=True,
        description="Allow credentials in CORS requests",
    )

    # -------------------------------------------------------------------------
    # Timeouts
    # -------------------------------------------------------------------------
    agent_timeout_seconds: int = Field(
        default=300,
        description="Timeout for agent execution in seconds (default 5 minutes)",
    )
    pipeline_timeout_seconds: int = Field(
        default=600,
        description="Timeout for full pipeline execution in seconds (default 10 minutes)",
    )

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.app_env == "development"

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        """Validate that production settings are secure."""
        if self.app_env == "production":
            errors = []

            # API key must be enabled in production
            if not self.api_key_enabled:
                errors.append("api_key_enabled must be True in production")

            # API key must be set if enabled
            if self.api_key_enabled and not self.api_key:
                errors.append("api_key must be set when api_key_enabled is True")

            # Debug must be disabled in production
            if self.debug:
                errors.append("debug must be False in production")

            # CORS cannot allow all origins in production
            if "*" in self.cors_allowed_origins:
                errors.append("cors_allowed_origins cannot contain '*' in production")

            if errors:
                raise ValueError(
                    f"Production configuration errors: {'; '.join(errors)}"
                )

        return self


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
