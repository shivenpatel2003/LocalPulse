"""Rate limiter factory with Redis and in-memory implementations.

Provides a consistent interface for rate limiting with automatic
fallback to in-memory when Redis is unavailable.

Usage:
    # Get rate limiter (auto-selects Redis or in-memory)
    limiter = await get_rate_limiter(settings)

    # Use consistently regardless of backend
    result = await limiter.is_allowed("api:google", limit=100, window=60)
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Protocol

import structlog

from src.config.settings import Settings

logger = structlog.get_logger(__name__)


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    remaining: int
    reset_at: float
    retry_after: Optional[float] = None


class RateLimiter(Protocol):
    """Protocol for rate limiter implementations."""

    async def is_allowed(
        self, identifier: str, limit: int, window: int
    ) -> RateLimitResult: ...

    async def get_status(
        self, identifier: str, limit: int, window: int
    ) -> RateLimitResult: ...

    async def reset(self, identifier: str) -> None: ...


@dataclass
class InMemoryRateLimiter:
    """
    In-memory rate limiter for development or Redis fallback.

    WARNING: Does not persist across restarts and does not share
    state between multiple application instances.
    """

    _buckets: Dict[str, list] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def is_allowed(
        self,
        identifier: str,
        limit: int,
        window: int,
    ) -> RateLimitResult:
        """Check if request is allowed."""
        async with self._lock:
            now = time.time()
            window_start = now - window

            # Initialize or clean bucket
            if identifier not in self._buckets:
                self._buckets[identifier] = []

            # Remove old entries
            self._buckets[identifier] = [
                t for t in self._buckets[identifier] if t > window_start
            ]

            current_count = len(self._buckets[identifier])
            remaining = max(0, limit - current_count)

            # Calculate reset time
            if self._buckets[identifier]:
                reset_at = min(self._buckets[identifier]) + window
            else:
                reset_at = now + window

            if current_count >= limit:
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    reset_at=reset_at,
                    retry_after=reset_at - now,
                )

            # Record request
            self._buckets[identifier].append(now)

            return RateLimitResult(
                allowed=True,
                remaining=remaining - 1,
                reset_at=reset_at,
            )

    async def get_status(
        self,
        identifier: str,
        limit: int,
        window: int,
    ) -> RateLimitResult:
        """Get status without consuming a request."""
        async with self._lock:
            now = time.time()
            window_start = now - window

            if identifier not in self._buckets:
                return RateLimitResult(
                    allowed=True,
                    remaining=limit,
                    reset_at=now + window,
                )

            # Clean old entries
            bucket = [t for t in self._buckets[identifier] if t > window_start]
            current_count = len(bucket)
            remaining = max(0, limit - current_count)

            if bucket:
                reset_at = min(bucket) + window
            else:
                reset_at = now + window

            return RateLimitResult(
                allowed=remaining > 0,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=max(0, reset_at - now) if remaining == 0 else None,
            )

    async def reset(self, identifier: str) -> None:
        """Reset rate limit for identifier."""
        async with self._lock:
            if identifier in self._buckets:
                del self._buckets[identifier]


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


async def get_rate_limiter(settings: Optional[Settings] = None) -> RateLimiter:
    """
    Get or create rate limiter instance.

    Attempts to use Redis if configured, falls back to in-memory.

    Args:
        settings: Application settings (uses get_settings() if not provided)

    Returns:
        Rate limiter instance (Redis or in-memory)
    """
    global _rate_limiter

    if _rate_limiter is not None:
        return _rate_limiter

    if settings is None:
        from src.config.settings import get_settings
        settings = get_settings()

    # Try Redis first
    if settings.redis_url:
        try:
            from src.core.redis_rate_limit import RedisRateLimiter

            redis_limiter = RedisRateLimiter(
                redis_url=settings.redis_url,
                key_prefix="localpulse:ratelimit",
            )
            await redis_limiter.connect()
            _rate_limiter = redis_limiter
            logger.info("rate_limiter_initialized", backend="redis")
            return _rate_limiter
        except Exception as e:
            logger.warning(
                "redis_rate_limiter_failed_fallback_to_memory",
                error=str(e),
            )

    # Fallback to in-memory
    _rate_limiter = InMemoryRateLimiter()
    logger.info("rate_limiter_initialized", backend="in_memory")
    return _rate_limiter


async def reset_rate_limiter() -> None:
    """Reset global rate limiter (for testing)."""
    global _rate_limiter
    _rate_limiter = None
