"""Redis-backed rate limiter with persistence across restarts.

Uses sliding window algorithm with Redis sorted sets for accurate rate limiting.
Supports horizontal scaling - multiple app instances share the same rate limit.

Usage:
    limiter = RedisRateLimiter(
        redis_url="redis://localhost:6379",
        key_prefix="localpulse:ratelimit"
    )
    await limiter.connect()

    # Check if request is allowed
    allowed, retry_after = await limiter.is_allowed("google_places", limit=100, window=60)
    if not allowed:
        raise RateLimitExceeded(f"Retry after {retry_after} seconds")
"""

import time
from dataclasses import dataclass
from typing import Optional

import structlog
import redis.asyncio as redis

logger = structlog.get_logger(__name__)


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    remaining: int
    reset_at: float
    retry_after: Optional[float] = None


class RedisRateLimiter:
    """
    Redis-backed rate limiter using sliding window algorithm.

    Uses Redis sorted sets where:
    - Score = timestamp of request
    - Member = unique request ID (timestamp + random suffix)

    This allows accurate counting within the sliding window.

    Args:
        redis_url: Redis connection URL
        key_prefix: Prefix for Redis keys (default: "ratelimit")
    """

    def __init__(
        self,
        redis_url: str,
        key_prefix: str = "localpulse:ratelimit",
    ):
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._client: Optional[redis.Redis] = None
        self._connected = False

    async def connect(self) -> None:
        """Establish Redis connection."""
        if self._connected:
            return

        try:
            self._client = redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            # Test connection
            await self._client.ping()
            self._connected = True
            logger.info("redis_rate_limiter_connected", url=self._redis_url)
        except Exception as e:
            logger.error("redis_rate_limiter_connection_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._connected = False
            logger.info("redis_rate_limiter_disconnected")

    @property
    def is_connected(self) -> bool:
        """Check if connected to Redis."""
        return self._connected

    def _make_key(self, identifier: str) -> str:
        """Create Redis key for rate limit bucket."""
        return f"{self._key_prefix}:{identifier}"

    async def is_allowed(
        self,
        identifier: str,
        limit: int,
        window: int,
    ) -> RateLimitResult:
        """
        Check if request is allowed under rate limit.

        Uses sliding window: counts requests in the last `window` seconds.

        Args:
            identifier: Unique identifier (e.g., "google_places", "user:123")
            limit: Maximum requests allowed in window
            window: Window size in seconds

        Returns:
            RateLimitResult with allowed status and metadata
        """
        if not self._connected:
            raise RuntimeError("Rate limiter not connected. Call connect() first.")

        key = self._make_key(identifier)
        now = time.time()
        window_start = now - window

        # Use pipeline for atomic operations
        pipe = self._client.pipeline()

        # Remove old entries outside the window
        pipe.zremrangebyscore(key, 0, window_start)

        # Count current entries in window
        pipe.zcard(key)

        # Get oldest entry for reset time calculation
        pipe.zrange(key, 0, 0, withscores=True)

        results = await pipe.execute()
        current_count = results[1]
        oldest_entry = results[2]

        # Calculate reset time
        if oldest_entry:
            oldest_time = oldest_entry[0][1]
            reset_at = oldest_time + window
        else:
            reset_at = now + window

        remaining = max(0, limit - current_count)

        if current_count >= limit:
            # Rate limited
            retry_after = reset_at - now
            logger.warning(
                "rate_limit_exceeded",
                identifier=identifier,
                limit=limit,
                current=current_count,
                retry_after=retry_after,
            )
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=reset_at,
                retry_after=retry_after,
            )

        # Request allowed - record it
        request_id = f"{now}:{id(self)}"
        await self._client.zadd(key, {request_id: now})

        # Set TTL to auto-cleanup (window + buffer)
        await self._client.expire(key, window + 60)

        logger.debug(
            "rate_limit_allowed",
            identifier=identifier,
            remaining=remaining - 1,
            reset_at=reset_at,
        )

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
        """
        Get current rate limit status without consuming a request.

        Args:
            identifier: Unique identifier
            limit: Maximum requests in window
            window: Window size in seconds

        Returns:
            Current status without recording a request
        """
        if not self._connected:
            raise RuntimeError("Rate limiter not connected.")

        key = self._make_key(identifier)
        now = time.time()
        window_start = now - window

        # Clean old entries and count
        pipe = self._client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zrange(key, 0, 0, withscores=True)

        results = await pipe.execute()
        current_count = results[1]
        oldest_entry = results[2]

        if oldest_entry:
            reset_at = oldest_entry[0][1] + window
        else:
            reset_at = now + window

        remaining = max(0, limit - current_count)

        return RateLimitResult(
            allowed=remaining > 0,
            remaining=remaining,
            reset_at=reset_at,
            retry_after=max(0, reset_at - now) if remaining == 0 else None,
        )

    async def reset(self, identifier: str) -> None:
        """Reset rate limit for an identifier."""
        if not self._connected:
            raise RuntimeError("Rate limiter not connected.")

        key = self._make_key(identifier)
        await self._client.delete(key)
        logger.info("rate_limit_reset", identifier=identifier)

    async def reset_all(self) -> int:
        """Reset all rate limits. Returns count of keys deleted."""
        if not self._connected:
            raise RuntimeError("Rate limiter not connected.")

        pattern = f"{self._key_prefix}:*"
        keys = []
        async for key in self._client.scan_iter(match=pattern):
            keys.append(key)

        if keys:
            count = await self._client.delete(*keys)
            logger.info("rate_limits_reset_all", count=count)
            return count
        return 0
