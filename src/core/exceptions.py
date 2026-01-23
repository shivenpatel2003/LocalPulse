"""
Core exception hierarchy for LocalPulse.

Provides standardized exception types with categorization for retry logic.
All components should use these exceptions instead of generic Exception.
"""

from typing import Any, Optional


# =============================================================================
# Base Exceptions
# =============================================================================


class LocalPulseError(Exception):
    """Base exception for all LocalPulse errors."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class RetryableError(LocalPulseError):
    """
    Transient errors that should be retried.

    Examples: Rate limits, timeouts, temporary network issues.
    """

    pass


class PermanentError(LocalPulseError):
    """
    Errors that won't be fixed by retrying.

    Examples: Invalid input, missing required data, authentication failures.
    """

    pass


# =============================================================================
# Initialization Errors
# =============================================================================


class InitializationError(PermanentError):
    """Raised when a critical component fails to initialize."""

    def __init__(self, component: str, message: str, details: Optional[dict[str, Any]] = None):
        self.component = component
        super().__init__(f"[{component}] {message}", details)


# =============================================================================
# Collector Errors
# =============================================================================


class CollectorError(LocalPulseError):
    """Base exception for collector errors."""

    def __init__(
        self,
        collector_type: str,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ):
        self.collector_type = collector_type
        super().__init__(f"[{collector_type}] {message}", details)


class CollectorRateLimitError(CollectorError, RetryableError):
    """Raised when a collector hits rate limits."""

    pass


class CollectorTimeoutError(CollectorError, RetryableError):
    """Raised when a collector operation times out."""

    pass


class CollectorAuthError(CollectorError, PermanentError):
    """Raised when collector authentication fails."""

    pass


class CollectorNotFoundError(CollectorError, PermanentError):
    """Raised when requested resource is not found."""

    pass


class CollectorUnavailableError(CollectorError, RetryableError):
    """Raised when collector service is temporarily unavailable."""

    pass


# =============================================================================
# Knowledge Store Errors
# =============================================================================


class KnowledgeStoreError(LocalPulseError):
    """Base exception for knowledge store errors."""

    pass


class KnowledgeStoreConnectionError(KnowledgeStoreError, RetryableError):
    """Raised when unable to connect to knowledge store."""

    pass


class KnowledgeStoreQueryError(KnowledgeStoreError, PermanentError):
    """Raised when a query is malformed or invalid."""

    pass


# =============================================================================
# Configuration Errors
# =============================================================================


class ConfigurationError(PermanentError):
    """Raised when configuration is invalid or missing."""

    def __init__(self, message: str, config_key: Optional[str] = None):
        self.config_key = config_key
        details = {"config_key": config_key} if config_key else None
        super().__init__(message, details)


# =============================================================================
# Circuit Breaker
# =============================================================================


class CircuitBreakerOpenError(RetryableError):
    """Raised when circuit breaker is open and blocking requests."""

    def __init__(self, service: str, recovery_time: float):
        self.service = service
        self.recovery_time = recovery_time
        super().__init__(
            f"Circuit breaker open for {service}. Recovery in {recovery_time:.1f}s",
            {"service": service, "recovery_time": recovery_time},
        )
