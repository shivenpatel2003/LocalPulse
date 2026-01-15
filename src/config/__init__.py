"""
Configuration Management.

This module provides centralized configuration using Pydantic Settings:

- settings: Main Settings class with environment variable loading
- industry_schema: Dynamic industry configuration models
- config_generator: AI-powered configuration generation
- config_loader: Load and cache configurations

Configuration sources (in order of precedence):
1. Environment variables
2. .env file
3. Default values

All sensitive values (API keys, passwords) are loaded from environment
variables and never committed to source control.

Example:
    from src.config import settings, IndustryConfig, load_config

    # Access configuration
    neo4j_uri = settings.neo4j_uri
    api_key = settings.anthropic_api_key

    # Load industry config for a client
    config = await load_config(client_id)

    # Settings are validated at startup
    # Invalid configuration will raise ValidationError
"""

from src.config.settings import Settings, get_settings, settings
from src.config.industry_schema import (
    IndustryConfig,
    DataFieldConfig,
    DataSourceConfig,
    ThemeConfig,
    CompetitorConfig,
    ReportConfig,
    ReportSection,
    GraphSchemaConfig,
    create_restaurant_template,
)
from src.config.config_loader import (
    load_config,
    load_config_or_default,
    save_config,
    get_config_accessor,
    ConfigAccessor,
    ConfigNotFoundError,
    ConfigValidationError,
)
from src.config.config_generator import (
    ConfigGenerator,
    get_config_generator,
    generate_config_from_description,
)

__all__ = [
    # Settings
    "Settings",
    "get_settings",
    "settings",
    # Industry Schema
    "IndustryConfig",
    "DataFieldConfig",
    "DataSourceConfig",
    "ThemeConfig",
    "CompetitorConfig",
    "ReportConfig",
    "ReportSection",
    "GraphSchemaConfig",
    "create_restaurant_template",
    # Config Loader
    "load_config",
    "load_config_or_default",
    "save_config",
    "get_config_accessor",
    "ConfigAccessor",
    "ConfigNotFoundError",
    "ConfigValidationError",
    # Config Generator
    "ConfigGenerator",
    "get_config_generator",
    "generate_config_from_description",
]
