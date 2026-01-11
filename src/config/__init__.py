"""
Configuration Management.

This module provides centralized configuration using Pydantic Settings:

- settings: Main Settings class with environment variable loading

Configuration sources (in order of precedence):
1. Environment variables
2. .env file
3. Default values

All sensitive values (API keys, passwords) are loaded from environment
variables and never committed to source control.

Example:
    from src.config import settings

    # Access configuration
    neo4j_uri = settings.neo4j_uri
    api_key = settings.anthropic_api_key

    # Settings are validated at startup
    # Invalid configuration will raise ValidationError
"""
