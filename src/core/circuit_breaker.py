"""
Circuit Breaker pattern implementation for external API resilience.

Prevents cascading failures by stopping requests to failing services
and allowing them time to recover.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Failing service, requests blocked
- HALF_OPEN: Testing if service recovered

Usage:
    breaker = CircuitBreaker("google_places", failure_threshold=5, recovery_timeout=60)

    @breaker
    async def call_google_places():
        ...

    # Or manual usage:
    if breaker.can_execute():
        try:
            result = await call_api()
            breaker.record_success()
        except Exception as e:
            breaker.record_failure()
            raise
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

import structlog

from src.core.exceptions import CircuitBreakerOpenError

logger = structlog.get_logger(__name__)

# Lazy import for metrics to avoid circular imports
_metrics_imported = False
_update_circuit_breaker_state = None
_record_circuit_breaker_failure = None


def _ensure_metrics():
    """Lazily import metrics to avoid circular imports."""
    global _metrics_imported, _update_circuit_breaker_state, _record_circuit_breaker_failure
    if not _metrics_imported:
        try:
            from src.monitoring.metrics import (
                update_circuit_breaker_state,
                record_circuit_breaker_failure,
            )
            _update_circuit_breaker_state = update_circuit_breaker_state
            _record_circuit_breaker_failure = record_circuit_breaker_failure
        except ImportError:
            # Metrics not available, use no-ops
            _update_circuit_breaker_state = lambda *args: None
            _record_circuit_breaker_failure = lambda *args: None
        _metrics_imported = True

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for protecting external service calls.

    Args:
        name: Identifier for this circuit (e.g., "google_places")
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Seconds to wait before testing recovery
        success_threshold: Successes needed in half-open to close circuit
    """

    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 2

    # Internal state
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: Optional[float] = field(default=None, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, checking for recovery timeout."""
        if self._state == CircuitState.OPEN and self._last_failure_time:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info(
                    "circuit_breaker_half_open",
                    name=self.name,
                    message="Testing if service recovered",
                )
        return self._state

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests)."""
        return self.state == CircuitState.OPEN

    def can_execute(self) -> bool:
        """Check if a request can be executed."""
        state = self.state
        return state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def time_until_recovery(self) -> float:
        """Get seconds until circuit may recover."""
        if self._state != CircuitState.OPEN or not self._last_failure_time:
            return 0.0
        elapsed = time.time() - self._last_failure_time
        return max(0.0, self.recovery_timeout - elapsed)

    async def record_success(self) -> None:
        """Record a successful call."""
        _ensure_metrics()

        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    if _update_circuit_breaker_state:
                        _update_circuit_breaker_state(self.name, "closed")
                    logger.info(
                        "circuit_breaker_closed",
                        name=self.name,
                        message="Service recovered, circuit closed",
                    )
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    async def record_failure(self) -> None:
        """Record a failed call."""
        _ensure_metrics()

        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            # Record failure metric
            if _record_circuit_breaker_failure:
                _record_circuit_breaker_failure(self.name)

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open goes back to open
                self._state = CircuitState.OPEN
                if _update_circuit_breaker_state:
                    _update_circuit_breaker_state(self.name, "open")
                logger.warning(
                    "circuit_breaker_reopened",
                    name=self.name,
                    message="Service still failing, circuit reopened",
                )
            elif (
                self._state == CircuitState.CLOSED
                and self._failure_count >= self.failure_threshold
            ):
                self._state = CircuitState.OPEN
                if _update_circuit_breaker_state:
                    _update_circuit_breaker_state(self.name, "open")
                logger.warning(
                    "circuit_breaker_opened",
                    name=self.name,
                    failure_count=self._failure_count,
                    recovery_timeout=self.recovery_timeout,
                    message="Too many failures, circuit opened",
                )

    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        logger.info("circuit_breaker_reset", name=self.name)

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Use as decorator for async functions."""

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            if not self.can_execute():
                recovery_time = self.time_until_recovery()
                raise CircuitBreakerOpenError(self.name, recovery_time)

            try:
                result = await func(*args, **kwargs)
                await self.record_success()
                return result
            except Exception as e:
                await self.record_failure()
                raise

        return wrapper


# =============================================================================
# Global Circuit Breaker Registry
# =============================================================================


_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
) -> CircuitBreaker:
    """
    Get or create a circuit breaker by name.

    Args:
        name: Unique identifier for the circuit
        failure_threshold: Failures before opening
        recovery_timeout: Seconds before recovery test

    Returns:
        Circuit breaker instance (reused if already exists)
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
    return _circuit_breakers[name]


def get_all_circuit_breakers() -> dict[str, CircuitBreaker]:
    """Get all registered circuit breakers."""
    return _circuit_breakers.copy()


def reset_all_circuit_breakers() -> None:
    """Reset all circuit breakers to closed state."""
    for breaker in _circuit_breakers.values():
        breaker.reset()
