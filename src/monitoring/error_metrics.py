"""Error metrics persistence for failure pattern analysis.

Provides Redis-backed storage for error occurrences with time-based queries
for failure pattern analysis. Falls back to in-memory storage when Redis
is unavailable.

Usage:
    from src.monitoring.error_metrics import get_error_metrics_store

    store = get_error_metrics_store()
    await store.record_error(
        error_type="ValidationError",
        endpoint="/api/collect",
        message="Invalid client_id format"
    )

    # Query errors
    count = await store.get_error_count("ValidationError", window_minutes=60)
    top_errors = await store.get_top_errors(window_minutes=60, limit=10)
    trend = await store.get_error_trend("ValidationError", bucket_minutes=5, buckets=12)
"""

import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ErrorRecord:
    """Single error occurrence record."""

    error_type: str
    endpoint: str
    timestamp: float
    message: str = ""
    context: dict[str, Any] = field(default_factory=dict)


class ErrorMetricsStore:
    """Persistent error metrics storage for failure pattern analysis.

    Uses Redis sorted sets to store error occurrences with timestamps.
    Falls back to in-memory storage when Redis is unavailable.

    Key structure:
    - errors:{error_type} -> sorted set (score=timestamp, member=json(record))
    - errors:by_endpoint:{endpoint} -> sorted set
    - errors:counts:{error_type} -> string (counter)

    Args:
        redis_url: Redis connection URL (default: from REDIS_URL env var)
        retention_hours: How long to retain error records (default: 24 hours)
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        retention_hours: int = 24,
    ) -> None:
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self.retention_hours = retention_hours
        self.retention_seconds = retention_hours * 3600
        self._redis: Any = None
        self._use_redis = bool(self.redis_url)
        self._memory_store: dict[str, list[ErrorRecord]] = defaultdict(list)
        self._memory_counts: dict[str, int] = defaultdict(int)
        self._connected = False

    async def _get_redis(self) -> Any:
        """Get or create Redis connection."""
        if not self._use_redis:
            return None

        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                # Test connection
                await self._redis.ping()
                self._connected = True
                logger.info(
                    "error_metrics_store_connected",
                    redis_url=self._redis_url_masked,
                )
            except Exception as e:
                logger.warning(
                    "error_metrics_redis_unavailable",
                    error=str(e),
                    fallback="in-memory",
                )
                self._use_redis = False
                self._redis = None
                return None

        return self._redis

    @property
    def _redis_url_masked(self) -> str:
        """Return masked Redis URL for logging (hide password)."""
        if not self.redis_url:
            return "None"
        # Simple masking: redis://user:****@host:port
        if "@" in self.redis_url:
            parts = self.redis_url.split("@")
            return f"{parts[0].rsplit(':', 1)[0]}:****@{parts[-1]}"
        return self.redis_url

    async def record_error(
        self,
        error_type: str,
        endpoint: str,
        message: str = "",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record an error occurrence.

        Args:
            error_type: Error classification (e.g., "ValidationError", "RateLimitExceeded")
            endpoint: API endpoint where error occurred
            message: Error message
            context: Additional context for analysis
        """
        timestamp = time.time()
        record = ErrorRecord(
            error_type=error_type,
            endpoint=endpoint,
            timestamp=timestamp,
            message=message,
            context=context or {},
        )

        redis = await self._get_redis()
        if redis:
            member = json.dumps({
                "error_type": error_type,
                "endpoint": endpoint,
                "timestamp": timestamp,
                "message": message,
                "context": context or {},
            })

            pipe = redis.pipeline()

            # Store by error type
            pipe.zadd(f"errors:{error_type}", {member: timestamp})

            # Store by endpoint (URL-safe key)
            safe_endpoint = endpoint.replace("/", "_").strip("_")
            pipe.zadd(f"errors:by_endpoint:{safe_endpoint}", {member: timestamp})

            # Increment counter
            pipe.incr(f"errors:counts:{error_type}")

            # Clean up old entries
            cutoff = timestamp - self.retention_seconds
            pipe.zremrangebyscore(f"errors:{error_type}", 0, cutoff)
            pipe.zremrangebyscore(f"errors:by_endpoint:{safe_endpoint}", 0, cutoff)

            await pipe.execute()

            logger.debug(
                "error_recorded",
                error_type=error_type,
                endpoint=endpoint,
                storage="redis",
            )
        else:
            # In-memory fallback
            self._memory_store[error_type].append(record)
            self._memory_counts[error_type] += 1

            # Clean up old entries
            cutoff = timestamp - self.retention_seconds
            self._memory_store[error_type] = [
                r for r in self._memory_store[error_type] if r.timestamp > cutoff
            ]

            logger.debug(
                "error_recorded",
                error_type=error_type,
                endpoint=endpoint,
                storage="memory",
            )

    async def get_error_count(
        self,
        error_type: str,
        window_minutes: int = 60,
    ) -> int:
        """Get error count for a type within time window.

        Args:
            error_type: Error type to count
            window_minutes: Time window in minutes (default: 60)

        Returns:
            Number of errors in the window
        """
        redis = await self._get_redis()
        cutoff = time.time() - (window_minutes * 60)

        if redis:
            return await redis.zcount(f"errors:{error_type}", cutoff, "+inf")
        else:
            return sum(
                1
                for r in self._memory_store.get(error_type, [])
                if r.timestamp > cutoff
            )

    async def get_total_error_count(self, error_type: str) -> int:
        """Get total error count (all time within retention).

        Args:
            error_type: Error type to count

        Returns:
            Total error count since store started or within retention
        """
        redis = await self._get_redis()
        if redis:
            count = await redis.get(f"errors:counts:{error_type}")
            return int(count) if count else 0
        else:
            return self._memory_counts.get(error_type, 0)

    async def get_top_errors(
        self,
        window_minutes: int = 60,
        limit: int = 10,
    ) -> list[tuple[str, int]]:
        """Get top error types by count within time window.

        Args:
            window_minutes: Time window in minutes (default: 60)
            limit: Maximum number of error types to return (default: 10)

        Returns:
            List of (error_type, count) tuples sorted by count descending
        """
        redis = await self._get_redis()

        if redis:
            # Scan for error keys and count
            error_counts: list[tuple[str, int]] = []
            cursor = 0
            seen_types: set[str] = set()

            while True:
                cursor, keys = await redis.scan(
                    cursor, match="errors:counts:*", count=100
                )
                for key in keys:
                    error_type = key.replace("errors:counts:", "")
                    if error_type not in seen_types:
                        seen_types.add(error_type)
                        count = await self.get_error_count(error_type, window_minutes)
                        if count > 0:
                            error_counts.append((error_type, count))

                if cursor == 0:
                    break

            return sorted(error_counts, key=lambda x: x[1], reverse=True)[:limit]
        else:
            cutoff = time.time() - (window_minutes * 60)
            error_counts = []

            for error_type, records in self._memory_store.items():
                count = sum(1 for r in records if r.timestamp > cutoff)
                if count > 0:
                    error_counts.append((error_type, count))

            return sorted(error_counts, key=lambda x: x[1], reverse=True)[:limit]

    async def get_error_trend(
        self,
        error_type: str,
        bucket_minutes: int = 5,
        buckets: int = 12,
    ) -> list[tuple[float, int]]:
        """Get error count trend over time buckets.

        Args:
            error_type: Error type to analyze
            bucket_minutes: Size of each time bucket in minutes (default: 5)
            buckets: Number of buckets to return (default: 12 = 1 hour)

        Returns:
            List of (bucket_start_timestamp, count) tuples from oldest to newest
        """
        now = time.time()
        bucket_seconds = bucket_minutes * 60
        results: list[tuple[float, int]] = []

        redis = await self._get_redis()

        for i in range(buckets - 1, -1, -1):
            bucket_end = now - (i * bucket_seconds)
            bucket_start = bucket_end - bucket_seconds

            if redis:
                count = await redis.zcount(
                    f"errors:{error_type}", bucket_start, bucket_end
                )
            else:
                count = sum(
                    1
                    for r in self._memory_store.get(error_type, [])
                    if bucket_start <= r.timestamp < bucket_end
                )

            results.append((bucket_start, count))

        return results

    async def get_errors_by_endpoint(
        self,
        endpoint: str,
        window_minutes: int = 60,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get recent errors for a specific endpoint.

        Args:
            endpoint: API endpoint to query
            window_minutes: Time window in minutes
            limit: Maximum number of errors to return

        Returns:
            List of error records as dictionaries
        """
        cutoff = time.time() - (window_minutes * 60)
        safe_endpoint = endpoint.replace("/", "_").strip("_")

        redis = await self._get_redis()
        if redis:
            key = f"errors:by_endpoint:{safe_endpoint}"
            raw_errors = await redis.zrangebyscore(
                key, cutoff, "+inf", start=0, num=limit
            )
            return [json.loads(e) for e in raw_errors]
        else:
            # In-memory: filter by endpoint across all types
            errors = []
            for records in self._memory_store.values():
                for r in records:
                    if r.endpoint == endpoint and r.timestamp > cutoff:
                        errors.append({
                            "error_type": r.error_type,
                            "endpoint": r.endpoint,
                            "timestamp": r.timestamp,
                            "message": r.message,
                            "context": r.context,
                        })

            errors.sort(key=lambda x: x["timestamp"], reverse=True)
            return errors[:limit]

    async def close(self) -> None:
        """Close Redis connection if open."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            self._connected = False
            logger.info("error_metrics_store_disconnected")


# Singleton instance
_error_metrics_store: Optional[ErrorMetricsStore] = None


def get_error_metrics_store() -> ErrorMetricsStore:
    """Get singleton ErrorMetricsStore instance.

    Returns:
        ErrorMetricsStore instance (singleton)
    """
    global _error_metrics_store
    if _error_metrics_store is None:
        _error_metrics_store = ErrorMetricsStore()
    return _error_metrics_store


def reset_error_metrics_store() -> None:
    """Reset singleton instance (useful for testing)."""
    global _error_metrics_store
    _error_metrics_store = None
