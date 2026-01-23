"""Unit tests for rate limiter implementations."""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.rate_limiter import (
    InMemoryRateLimiter,
    RateLimitResult,
    get_rate_limiter,
    reset_rate_limiter,
)


class TestInMemoryRateLimiter:
    """Test in-memory rate limiter."""

    @pytest.fixture
    def limiter(self):
        """Fresh rate limiter for each test."""
        return InMemoryRateLimiter()

    @pytest.mark.asyncio
    async def test_allows_requests_under_limit(self, limiter):
        """Requests under limit are allowed."""
        result = await limiter.is_allowed("test", limit=5, window=60)

        assert result.allowed is True
        assert result.remaining == 4

    @pytest.mark.asyncio
    async def test_blocks_requests_over_limit(self, limiter):
        """Requests over limit are blocked."""
        # Use up the limit
        for _ in range(5):
            await limiter.is_allowed("test", limit=5, window=60)

        # Next request should be blocked
        result = await limiter.is_allowed("test", limit=5, window=60)

        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after is not None
        assert result.retry_after > 0

    @pytest.mark.asyncio
    async def test_different_identifiers_independent(self, limiter):
        """Different identifiers have independent limits."""
        # Max out identifier A
        for _ in range(5):
            await limiter.is_allowed("A", limit=5, window=60)

        # Identifier B should still work
        result = await limiter.is_allowed("B", limit=5, window=60)

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_reset_clears_limit(self, limiter):
        """Reset clears the rate limit."""
        # Use up the limit
        for _ in range(5):
            await limiter.is_allowed("test", limit=5, window=60)

        # Reset
        await limiter.reset("test")

        # Should be allowed again
        result = await limiter.is_allowed("test", limit=5, window=60)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_get_status_does_not_consume(self, limiter):
        """get_status doesn't consume a request."""
        # Check status
        status1 = await limiter.get_status("test", limit=5, window=60)

        # Check again
        status2 = await limiter.get_status("test", limit=5, window=60)

        # Both should show full limit available
        assert status1.remaining == 5
        assert status2.remaining == 5

    @pytest.mark.asyncio
    async def test_concurrent_requests_respect_limit(self, limiter):
        """Concurrent requests don't exceed limit."""

        async def make_request():
            return await limiter.is_allowed("concurrent", limit=5, window=60)

        # Make 10 concurrent requests
        results = await asyncio.gather(*[make_request() for _ in range(10)])

        # Exactly 5 should be allowed
        allowed_count = sum(1 for r in results if r.allowed)
        assert allowed_count == 5


class TestRateLimiterFactory:
    """Test rate limiter factory function."""

    @pytest.fixture(autouse=True)
    async def cleanup(self):
        """Reset global limiter after each test."""
        yield
        await reset_rate_limiter()

    @pytest.mark.asyncio
    async def test_returns_in_memory_when_no_redis(self):
        """Returns in-memory limiter when Redis not configured."""
        mock_settings = MagicMock()
        mock_settings.redis_url = None

        limiter = await get_rate_limiter(mock_settings)

        assert isinstance(limiter, InMemoryRateLimiter)

    @pytest.mark.asyncio
    async def test_returns_redis_when_configured(self):
        """Returns Redis limiter when configured and available."""
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379"

        with patch("src.core.redis_rate_limit.RedisRateLimiter") as MockRedis:
            mock_instance = AsyncMock()
            mock_instance.connect = AsyncMock()
            MockRedis.return_value = mock_instance

            limiter = await get_rate_limiter(mock_settings)

            MockRedis.assert_called_once()
            mock_instance.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_memory_on_redis_error(self):
        """Falls back to in-memory when Redis connection fails."""
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379"

        with patch("src.core.redis_rate_limit.RedisRateLimiter") as MockRedis:
            mock_instance = AsyncMock()
            mock_instance.connect = AsyncMock(side_effect=Exception("Connection refused"))
            MockRedis.return_value = mock_instance

            limiter = await get_rate_limiter(mock_settings)

            # Should fall back to in-memory
            assert isinstance(limiter, InMemoryRateLimiter)

    @pytest.mark.asyncio
    async def test_reuses_existing_instance(self):
        """Factory reuses existing limiter instance."""
        mock_settings = MagicMock()
        mock_settings.redis_url = None

        limiter1 = await get_rate_limiter(mock_settings)
        limiter2 = await get_rate_limiter(mock_settings)

        assert limiter1 is limiter2
