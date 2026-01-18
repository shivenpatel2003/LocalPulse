"""Collector registry for runtime collector selection.

Provides decorator-based registration and factory function for collectors.
"""

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.collectors.base import BaseCollector


class CollectorType(Enum):
    """Supported collector types."""

    TWITTER = "twitter"
    INSTAGRAM = "instagram"
    WEB = "web"
    CUSTOM_API = "custom_api"
    GOOGLE_PLACES = "google_places"


_collectors: dict[CollectorType, type["BaseCollector"]] = {}


def register_collector(collector_type: CollectorType):
    """Decorator to register a collector class.

    Args:
        collector_type: The CollectorType enum value for this collector.

    Returns:
        Decorator function that registers the class.

    Example:
        @register_collector(CollectorType.INSTAGRAM)
        class InstagramCollector(BaseCollector):
            ...
    """

    def decorator(cls: type["BaseCollector"]):
        _collectors[collector_type] = cls
        return cls

    return decorator


def get_collector(collector_type: CollectorType, config: dict) -> "BaseCollector":
    """Factory function to get a collector instance.

    Args:
        collector_type: The type of collector to instantiate.
        config: Configuration dictionary for the collector.

    Returns:
        Instantiated collector.

    Raises:
        ValueError: If the collector type is not registered.
    """
    if collector_type not in _collectors:
        raise ValueError(f"Unknown collector type: {collector_type}")
    return _collectors[collector_type](config)


def list_collectors() -> list[CollectorType]:
    """List all registered collector types.

    Returns:
        List of registered CollectorType values.
    """
    return list(_collectors.keys())
