"""
Monitoring and observability for LocalPulse.

Provides Prometheus metrics for tracking system health and performance,
with persistent error metrics storage for failure pattern analysis.

Usage:
    from src.monitoring import track_agent_execution, record_error

    # Track agent execution
    with track_agent_execution("research"):
        await agent.execute(query)

    # Record errors (Prometheus + Redis persistence)
    await record_error("ValidationError", "/api/collect", "Invalid input")

    # Query error patterns
    from src.monitoring import get_error_metrics_store
    store = get_error_metrics_store()
    top_errors = await store.get_top_errors(window_minutes=60)
"""

from src.monitoring.error_metrics import (
    ErrorMetricsStore,
    ErrorRecord,
    get_error_metrics_store,
    reset_error_metrics_store,
)
from src.monitoring.metrics import (
    AGENT_EXECUTION_DURATION,
    API_REQUEST_DURATION,
    KNOWLEDGE_STORE_OPERATIONS,
    CIRCUIT_BREAKER_STATE,
    COLLECTOR_OPERATIONS,
    ERROR_COUNT,
    RATE_LIMIT_HITS,
    track_agent_execution,
    track_api_request,
    track_knowledge_store_operation,
    track_collector_operation,
    update_circuit_breaker_state,
    record_circuit_breaker_failure,
    record_error,
    record_rate_limit_hit,
    get_metrics_app,
)

__all__ = [
    # Prometheus metrics
    "AGENT_EXECUTION_DURATION",
    "API_REQUEST_DURATION",
    "KNOWLEDGE_STORE_OPERATIONS",
    "CIRCUIT_BREAKER_STATE",
    "COLLECTOR_OPERATIONS",
    "ERROR_COUNT",
    "RATE_LIMIT_HITS",
    # Context managers
    "track_agent_execution",
    "track_api_request",
    "track_knowledge_store_operation",
    "track_collector_operation",
    # Helper functions
    "update_circuit_breaker_state",
    "record_circuit_breaker_failure",
    "record_error",
    "record_rate_limit_hit",
    "get_metrics_app",
    # Error metrics store
    "ErrorMetricsStore",
    "ErrorRecord",
    "get_error_metrics_store",
    "reset_error_metrics_store",
]
