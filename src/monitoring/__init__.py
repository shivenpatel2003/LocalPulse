"""
Monitoring and observability for LocalPulse.

Provides Prometheus metrics for tracking system health and performance.
"""

from src.monitoring.metrics import (
    AGENT_EXECUTION_DURATION,
    API_REQUEST_DURATION,
    KNOWLEDGE_STORE_OPERATIONS,
    CIRCUIT_BREAKER_STATE,
    COLLECTOR_OPERATIONS,
    track_agent_execution,
    track_api_request,
    track_knowledge_store_operation,
    track_collector_operation,
    update_circuit_breaker_state,
    get_metrics_app,
)

__all__ = [
    "AGENT_EXECUTION_DURATION",
    "API_REQUEST_DURATION",
    "KNOWLEDGE_STORE_OPERATIONS",
    "CIRCUIT_BREAKER_STATE",
    "COLLECTOR_OPERATIONS",
    "track_agent_execution",
    "track_api_request",
    "track_knowledge_store_operation",
    "track_collector_operation",
    "update_circuit_breaker_state",
    "get_metrics_app",
]
