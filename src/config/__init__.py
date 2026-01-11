"""
Config Module

This module manages application configuration:
- Settings: Pydantic settings for environment variables
- Database: Database connection configuration
- Agents: Agent-specific configuration
- Logging: Structured logging configuration
"""

from .settings import Settings, get_settings

__all__ = [
    "Settings",
    "get_settings",
]
