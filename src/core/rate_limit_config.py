"""Rate limit configuration for different API endpoints and services.

Defines rate limits for various identifiers used throughout the application.
All limits use a sliding window algorithm.

Usage:
    from src.core.rate_limit_config import get_api_limits, RateLimitConfig

    # Get limits for API requests
    config = get_api_limits("api_requests")
    # config.requests_per_minute = 100
    # config.requests_per_hour = 1000
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class Duration(IntEnum):
    """Time durations in seconds for rate limiting."""

    SECOND = 1
    MINUTE = 60
    HOUR = 3600
    DAY = 86400


@dataclass
class Rate:
    """A rate limit specification."""

    limit: int
    window: Duration

    def __repr__(self) -> str:
        duration_name = {
            Duration.SECOND: "second",
            Duration.MINUTE: "minute",
            Duration.HOUR: "hour",
            Duration.DAY: "day",
        }.get(self.window, f"{self.window}s")
        return f"Rate({self.limit}/{duration_name})"


@dataclass
class RateLimitConfig:
    """Configuration for a rate-limited resource."""

    name: str
    rates: list[Rate]
    description: str = ""

    @property
    def requests_per_minute(self) -> Optional[int]:
        """Get the per-minute limit if defined."""
        for rate in self.rates:
            if rate.window == Duration.MINUTE:
                return rate.limit
        return None

    @property
    def requests_per_hour(self) -> Optional[int]:
        """Get the per-hour limit if defined."""
        for rate in self.rates:
            if rate.window == Duration.HOUR:
                return rate.limit
        return None


# =============================================================================
# API Rate Limits
# =============================================================================

API_LIMITS: dict[str, RateLimitConfig] = {
    # API endpoint rate limiting
    "api_requests": RateLimitConfig(
        name="api_requests",
        description="General API request rate limiting per client",
        rates=[
            Rate(100, Duration.MINUTE),   # 100 requests per minute
            Rate(1000, Duration.HOUR),    # 1000 requests per hour
        ],
    ),

    # Google Places API
    "google_places": RateLimitConfig(
        name="google_places",
        description="Google Places API rate limits",
        rates=[
            Rate(10, Duration.SECOND),    # 10 QPS (within Google's limits)
            Rate(500, Duration.MINUTE),   # 500 per minute
        ],
    ),

    # LLM API calls (Claude/OpenAI)
    "llm_api": RateLimitConfig(
        name="llm_api",
        description="LLM API rate limits (expensive operations)",
        rates=[
            Rate(20, Duration.MINUTE),    # 20 requests per minute
            Rate(200, Duration.HOUR),     # 200 per hour
        ],
    ),

    # Embedding generation
    "embeddings": RateLimitConfig(
        name="embeddings",
        description="Embedding API rate limits",
        rates=[
            Rate(100, Duration.MINUTE),   # 100 per minute
            Rate(3000, Duration.HOUR),    # 3000 per hour
        ],
    ),

    # Email sending (SendGrid)
    "email": RateLimitConfig(
        name="email",
        description="Email sending rate limits",
        rates=[
            Rate(5, Duration.MINUTE),     # 5 emails per minute
            Rate(100, Duration.HOUR),     # 100 per hour
        ],
    ),
}


def get_api_limits(identifier: str) -> Optional[RateLimitConfig]:
    """
    Get rate limit configuration for an identifier.

    Args:
        identifier: The rate limit identifier (e.g., "api_requests", "google_places")

    Returns:
        RateLimitConfig if found, None otherwise
    """
    return API_LIMITS.get(identifier)


def get_rate_for_window(identifier: str, window: Duration) -> Optional[Rate]:
    """
    Get a specific rate limit for an identifier and window.

    Args:
        identifier: The rate limit identifier
        window: The time window duration

    Returns:
        Rate if found for that window, None otherwise
    """
    config = get_api_limits(identifier)
    if config:
        for rate in config.rates:
            if rate.window == window:
                return rate
    return None


# Convenience function to get the primary (first) rate limit
def get_primary_rate(identifier: str) -> Optional[tuple[int, int]]:
    """
    Get the primary rate limit (first defined) as (limit, window_seconds).

    Args:
        identifier: The rate limit identifier

    Returns:
        Tuple of (limit, window_in_seconds) or None
    """
    config = get_api_limits(identifier)
    if config and config.rates:
        rate = config.rates[0]
        return (rate.limit, int(rate.window))
    return None
