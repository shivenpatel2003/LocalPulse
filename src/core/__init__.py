"""
Core infrastructure modules for LocalPulse.

Provides common utilities used across the application:
- exceptions: Standardized exception hierarchy
- circuit_breaker: Resilience pattern for external APIs
"""

from src.core.exceptions import (
    LocalPulseError,
    RetryableError,
    PermanentError,
    InitializationError,
    CollectorError,
    CollectorRateLimitError,
    CollectorTimeoutError,
    CollectorAuthError,
    CollectorNotFoundError,
    CollectorUnavailableError,
    KnowledgeStoreError,
    KnowledgeStoreConnectionError,
    KnowledgeStoreQueryError,
    ConfigurationError,
    CircuitBreakerOpenError,
)

from src.core.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    get_circuit_breaker,
    get_all_circuit_breakers,
    reset_all_circuit_breakers,
)

from src.core.container import (
    DependencyContainer,
    get_container,
    initialize_container,
    shutdown_container,
)

__all__ = [
    # Exceptions
    "LocalPulseError",
    "RetryableError",
    "PermanentError",
    "InitializationError",
    "CollectorError",
    "CollectorRateLimitError",
    "CollectorTimeoutError",
    "CollectorAuthError",
    "CollectorNotFoundError",
    "CollectorUnavailableError",
    "KnowledgeStoreError",
    "KnowledgeStoreConnectionError",
    "KnowledgeStoreQueryError",
    "ConfigurationError",
    "CircuitBreakerOpenError",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitState",
    "get_circuit_breaker",
    "get_all_circuit_breakers",
    "reset_all_circuit_breakers",
    # Dependency Container
    "DependencyContainer",
    "get_container",
    "initialize_container",
    "shutdown_container",
]
