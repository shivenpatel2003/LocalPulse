"""
Prometheus metrics for LocalPulse observability.

Provides standardized metrics for monitoring system performance,
health, and resource usage.

Usage:
    from src.monitoring.metrics import track_agent_execution

    with track_agent_execution("research"):
        await agent.execute(query)

    # Or manually
    AGENT_EXECUTION_DURATION.labels(agent="research").observe(duration)
"""

import time
from contextlib import contextmanager
from typing import Generator

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route


# =============================================================================
# Metric Definitions
# =============================================================================

# Agent execution metrics
AGENT_EXECUTION_DURATION = Histogram(
    "localpulse_agent_execution_duration_seconds",
    "Duration of agent execution in seconds",
    ["agent"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

AGENT_EXECUTION_TOTAL = Counter(
    "localpulse_agent_execution_total",
    "Total number of agent executions",
    ["agent", "status"],
)

# API request metrics
API_REQUEST_DURATION = Histogram(
    "localpulse_api_request_duration_seconds",
    "Duration of API requests in seconds",
    ["method", "endpoint", "status_code"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

API_REQUEST_TOTAL = Counter(
    "localpulse_api_request_total",
    "Total number of API requests",
    ["method", "endpoint", "status_code"],
)

# Knowledge store metrics
KNOWLEDGE_STORE_OPERATIONS = Counter(
    "localpulse_knowledge_store_operations_total",
    "Total knowledge store operations",
    ["store", "operation", "status"],
)

KNOWLEDGE_STORE_LATENCY = Histogram(
    "localpulse_knowledge_store_latency_seconds",
    "Latency of knowledge store operations",
    ["store", "operation"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# Circuit breaker metrics
CIRCUIT_BREAKER_STATE = Gauge(
    "localpulse_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half_open, 2=open)",
    ["service"],
)

CIRCUIT_BREAKER_FAILURES = Counter(
    "localpulse_circuit_breaker_failures_total",
    "Total failures recorded by circuit breakers",
    ["service"],
)

# Collector metrics
COLLECTOR_OPERATIONS = Counter(
    "localpulse_collector_operations_total",
    "Total collector operations",
    ["collector", "operation", "status"],
)

COLLECTOR_LATENCY = Histogram(
    "localpulse_collector_latency_seconds",
    "Latency of collector operations",
    ["collector", "operation"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)


# =============================================================================
# Tracking Context Managers
# =============================================================================


@contextmanager
def track_agent_execution(agent_name: str) -> Generator[None, None, None]:
    """
    Context manager to track agent execution duration and status.

    Usage:
        with track_agent_execution("research"):
            await agent.execute(query)
    """
    start_time = time.perf_counter()
    status = "success"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.perf_counter() - start_time
        AGENT_EXECUTION_DURATION.labels(agent=agent_name).observe(duration)
        AGENT_EXECUTION_TOTAL.labels(agent=agent_name, status=status).inc()


@contextmanager
def track_api_request(
    method: str,
    endpoint: str,
) -> Generator[dict, None, None]:
    """
    Context manager to track API request duration and status.

    Usage:
        with track_api_request("GET", "/api/health") as ctx:
            response = await call_endpoint()
            ctx["status_code"] = response.status_code
    """
    start_time = time.perf_counter()
    context = {"status_code": "500"}  # Default to error
    try:
        yield context
    finally:
        duration = time.perf_counter() - start_time
        status_code = str(context.get("status_code", "500"))
        API_REQUEST_DURATION.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code,
        ).observe(duration)
        API_REQUEST_TOTAL.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code,
        ).inc()


@contextmanager
def track_knowledge_store_operation(
    store: str,
    operation: str,
) -> Generator[None, None, None]:
    """
    Context manager to track knowledge store operations.

    Usage:
        with track_knowledge_store_operation("neo4j", "query"):
            result = await neo4j.run_query(...)
    """
    start_time = time.perf_counter()
    status = "success"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.perf_counter() - start_time
        KNOWLEDGE_STORE_OPERATIONS.labels(
            store=store,
            operation=operation,
            status=status,
        ).inc()
        KNOWLEDGE_STORE_LATENCY.labels(
            store=store,
            operation=operation,
        ).observe(duration)


@contextmanager
def track_collector_operation(
    collector: str,
    operation: str,
) -> Generator[None, None, None]:
    """
    Context manager to track collector operations.

    Usage:
        with track_collector_operation("instagram", "scrape_posts"):
            posts = await collector.collect_user_posts(username)
    """
    start_time = time.perf_counter()
    status = "success"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.perf_counter() - start_time
        COLLECTOR_OPERATIONS.labels(
            collector=collector,
            operation=operation,
            status=status,
        ).inc()
        COLLECTOR_LATENCY.labels(
            collector=collector,
            operation=operation,
        ).observe(duration)


def update_circuit_breaker_state(service: str, state: str) -> None:
    """
    Update circuit breaker state gauge.

    Args:
        service: Service name
        state: Circuit state ("closed", "half_open", "open")
    """
    state_map = {"closed": 0, "half_open": 1, "open": 2}
    CIRCUIT_BREAKER_STATE.labels(service=service).set(state_map.get(state, 0))


def record_circuit_breaker_failure(service: str) -> None:
    """Record a circuit breaker failure."""
    CIRCUIT_BREAKER_FAILURES.labels(service=service).inc()


# =============================================================================
# Metrics Endpoint
# =============================================================================


async def metrics_endpoint(request) -> Response:
    """Prometheus metrics endpoint handler."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


def get_metrics_app() -> Starlette:
    """
    Get a Starlette app for serving metrics.

    Mount this at /metrics in your main app:
        from src.monitoring.metrics import get_metrics_app
        app.mount("/metrics", get_metrics_app())
    """
    return Starlette(
        routes=[
            Route("/", metrics_endpoint),
        ]
    )
