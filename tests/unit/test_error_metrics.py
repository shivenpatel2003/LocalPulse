"""Unit tests for error metrics persistence.

Tests ErrorMetricsStore with in-memory backend and mocked Redis.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.monitoring.error_metrics import (
    ErrorMetricsStore,
    ErrorRecord,
    get_error_metrics_store,
    reset_error_metrics_store,
)


class TestErrorRecord:
    """Tests for ErrorRecord dataclass."""

    def test_error_record_creation(self):
        """Test creating an ErrorRecord with all fields."""
        record = ErrorRecord(
            error_type="ValidationError",
            endpoint="/api/test",
            timestamp=1234567890.0,
            message="Invalid input",
            context={"field": "email"},
        )

        assert record.error_type == "ValidationError"
        assert record.endpoint == "/api/test"
        assert record.timestamp == 1234567890.0
        assert record.message == "Invalid input"
        assert record.context == {"field": "email"}

    def test_error_record_defaults(self):
        """Test ErrorRecord default values."""
        record = ErrorRecord(
            error_type="TestError",
            endpoint="/test",
            timestamp=1000.0,
        )

        assert record.message == ""
        assert record.context == {}


class TestErrorMetricsStore:
    """Tests for ErrorMetricsStore with in-memory backend."""

    @pytest.fixture
    def store(self):
        """Create store with in-memory backend (no Redis URL)."""
        return ErrorMetricsStore(redis_url=None)

    @pytest.mark.asyncio
    async def test_record_error_in_memory(self, store):
        """Test recording errors to in-memory store."""
        await store.record_error(
            error_type="ValidationError",
            endpoint="/api/test",
            message="Invalid input",
        )

        count = await store.get_error_count("ValidationError", window_minutes=60)
        assert count == 1

    @pytest.mark.asyncio
    async def test_record_multiple_errors(self, store):
        """Test recording multiple errors of same type."""
        for i in range(5):
            await store.record_error(
                error_type="TestError",
                endpoint="/test",
                message=f"Error {i}",
            )

        count = await store.get_error_count("TestError", window_minutes=60)
        assert count == 5

    @pytest.mark.asyncio
    async def test_get_total_error_count(self, store):
        """Test getting total error count."""
        for _ in range(5):
            await store.record_error(error_type="TestError", endpoint="/test")

        total = await store.get_total_error_count("TestError")
        assert total == 5

    @pytest.mark.asyncio
    async def test_get_error_count_nonexistent(self, store):
        """Test getting count for nonexistent error type."""
        count = await store.get_error_count("NonexistentError", window_minutes=60)
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_top_errors(self, store):
        """Test getting top errors by count."""
        # Record different error types with varying counts
        for _ in range(10):
            await store.record_error("HighFreqError", "/test")
        for _ in range(5):
            await store.record_error("MedFreqError", "/test")
        for _ in range(2):
            await store.record_error("LowFreqError", "/test")

        top = await store.get_top_errors(window_minutes=60, limit=5)

        assert len(top) == 3
        assert top[0][0] == "HighFreqError"
        assert top[0][1] == 10
        assert top[1][0] == "MedFreqError"
        assert top[1][1] == 5
        assert top[2][0] == "LowFreqError"
        assert top[2][1] == 2

    @pytest.mark.asyncio
    async def test_get_top_errors_with_limit(self, store):
        """Test that limit parameter works correctly."""
        for i in range(5):
            for _ in range(i + 1):
                await store.record_error(f"Error{i}", "/test")

        top = await store.get_top_errors(window_minutes=60, limit=2)

        assert len(top) == 2
        assert top[0][0] == "Error4"  # Highest count (5)
        assert top[1][0] == "Error3"  # Second highest (4)

    @pytest.mark.asyncio
    async def test_get_error_trend(self, store):
        """Test getting error trend over time."""
        # Record some errors
        await store.record_error("TrendError", "/test")
        await store.record_error("TrendError", "/test")

        trend = await store.get_error_trend("TrendError", bucket_minutes=1, buckets=5)

        assert len(trend) == 5
        # Each entry is (timestamp, count) tuple
        for bucket_start, count in trend:
            assert isinstance(bucket_start, float)
            assert isinstance(count, int)
            assert count >= 0

        # Most recent bucket should have our errors
        total_in_trend = sum(count for _, count in trend)
        assert total_in_trend == 2

    @pytest.mark.asyncio
    async def test_error_with_context(self, store):
        """Test recording error with context data."""
        await store.record_error(
            error_type="ContextError",
            endpoint="/api/context",
            message="Error with context",
            context={"user_id": "123", "action": "create", "payload_size": 1024},
        )

        count = await store.get_error_count("ContextError")
        assert count == 1

    @pytest.mark.asyncio
    async def test_get_errors_by_endpoint(self, store):
        """Test getting errors filtered by endpoint."""
        await store.record_error("Error1", "/api/endpoint1", "First error")
        await store.record_error("Error2", "/api/endpoint1", "Second error")
        await store.record_error("Error3", "/api/endpoint2", "Different endpoint")

        errors = await store.get_errors_by_endpoint("/api/endpoint1", window_minutes=60)

        assert len(errors) == 2
        for error in errors:
            assert error["endpoint"] == "/api/endpoint1"

    @pytest.mark.asyncio
    async def test_redis_fallback_on_failure(self):
        """Test graceful fallback when Redis unavailable."""
        # Use invalid Redis URL to force fallback
        store = ErrorMetricsStore(redis_url="redis://invalid:6379")

        # Should not raise, falls back to in-memory
        await store.record_error("FallbackError", "/test")
        count = await store.get_error_count("FallbackError")
        assert count == 1
        assert store._use_redis is False  # Should have switched to in-memory


class TestErrorMetricsSingleton:
    """Tests for singleton pattern."""

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_error_metrics_store()

    def test_get_error_metrics_store_returns_singleton(self):
        """Test that get_error_metrics_store returns same instance."""
        store1 = get_error_metrics_store()
        store2 = get_error_metrics_store()

        assert store1 is store2

    def test_reset_error_metrics_store(self):
        """Test that reset clears the singleton."""
        store1 = get_error_metrics_store()
        reset_error_metrics_store()
        store2 = get_error_metrics_store()

        assert store1 is not store2


class TestErrorMetricsIntegration:
    """Integration tests with metrics module."""

    @pytest.mark.asyncio
    async def test_record_error_function(self):
        """Test the record_error helper function from metrics module."""
        # Patch the source module where get_error_metrics_store is defined
        with patch(
            "src.monitoring.error_metrics.get_error_metrics_store"
        ) as mock_get_store:
            mock_store = AsyncMock()
            mock_get_store.return_value = mock_store

            from src.monitoring.metrics import record_error

            await record_error(
                error_type="IntegrationError",
                endpoint="/api/test",
                message="Test error",
                context={"test": True},
            )

            mock_store.record_error.assert_called_once_with(
                error_type="IntegrationError",
                endpoint="/api/test",
                message="Test error",
                context={"test": True},
            )

    @pytest.mark.asyncio
    async def test_record_error_handles_persistence_failure(self):
        """Test that record_error handles persistence failures gracefully."""
        with patch(
            "src.monitoring.error_metrics.get_error_metrics_store"
        ) as mock_get_store:
            mock_store = AsyncMock()
            mock_store.record_error.side_effect = Exception("Redis connection failed")
            mock_get_store.return_value = mock_store

            from src.monitoring.metrics import record_error

            # Should not raise - gracefully handles failure
            await record_error(
                error_type="TestError",
                endpoint="/test",
                message="Test",
            )

    @pytest.mark.asyncio
    async def test_record_error_skips_persistence_when_disabled(self):
        """Test that persist=False skips Redis storage."""
        with patch(
            "src.monitoring.error_metrics.get_error_metrics_store"
        ) as mock_get_store:
            mock_store = AsyncMock()
            mock_get_store.return_value = mock_store

            from src.monitoring.metrics import record_error

            await record_error(
                error_type="TestError",
                endpoint="/test",
                persist=False,
            )

            mock_store.record_error.assert_not_called()
