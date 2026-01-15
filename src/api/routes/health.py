"""Health check endpoints for the LocalPulse API.

Provides system health status including database connections and scheduler status.
"""

from datetime import datetime, timezone
import time
from typing import Optional

import structlog
from fastapi import APIRouter, Depends

from src.api.models import HealthCheckResponse, HealthStatus
from src.config.settings import get_settings, Settings

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Health"])

# Track server start time for uptime calculation
_server_start_time: Optional[float] = None


def set_server_start_time() -> None:
    """Set the server start time. Called on application startup."""
    global _server_start_time
    _server_start_time = time.time()


def get_uptime_seconds() -> Optional[float]:
    """Get server uptime in seconds."""
    if _server_start_time is None:
        return None
    return time.time() - _server_start_time


async def check_supabase_health(settings: Settings) -> HealthStatus:
    """Check Supabase database connectivity."""
    start_time = time.time()
    try:
        from supabase import create_client

        client = create_client(
            settings.supabase_url,
            settings.supabase_key.get_secret_value(),
        )
        # Simple query to check connectivity
        client.table("scheduled_jobs").select("id").limit(1).execute()
        latency = (time.time() - start_time) * 1000

        return HealthStatus(
            status="healthy",
            latency_ms=round(latency, 2),
            message="Connected to Supabase",
        )
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        logger.error("supabase_health_check_failed", error=str(e))
        return HealthStatus(
            status="unhealthy",
            latency_ms=round(latency, 2),
            message=f"Supabase connection failed: {str(e)[:100]}",
        )


async def check_neo4j_health(settings: Settings) -> HealthStatus:
    """Check Neo4j database connectivity."""
    start_time = time.time()
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        )
        with driver.session() as session:
            session.run("RETURN 1")
        driver.close()
        latency = (time.time() - start_time) * 1000

        return HealthStatus(
            status="healthy",
            latency_ms=round(latency, 2),
            message="Connected to Neo4j",
        )
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        logger.error("neo4j_health_check_failed", error=str(e))
        return HealthStatus(
            status="unhealthy",
            latency_ms=round(latency, 2),
            message=f"Neo4j connection failed: {str(e)[:100]}",
        )


async def check_pinecone_health(settings: Settings) -> HealthStatus:
    """Check Pinecone vector store connectivity."""
    start_time = time.time()
    try:
        from pinecone import Pinecone

        pc = Pinecone(api_key=settings.pinecone_api_key.get_secret_value())
        # List indexes to verify connectivity
        pc.list_indexes()
        latency = (time.time() - start_time) * 1000

        return HealthStatus(
            status="healthy",
            latency_ms=round(latency, 2),
            message="Connected to Pinecone",
        )
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        logger.error("pinecone_health_check_failed", error=str(e))
        return HealthStatus(
            status="unhealthy",
            latency_ms=round(latency, 2),
            message=f"Pinecone connection failed: {str(e)[:100]}",
        )


async def check_scheduler_health() -> HealthStatus:
    """Check scheduler status."""
    try:
        # Import here to avoid circular imports
        from src.api.dependencies import get_scheduler

        scheduler = get_scheduler()
        if scheduler and scheduler.is_running:
            return HealthStatus(
                status="healthy",
                message="Scheduler is running",
            )
        else:
            return HealthStatus(
                status="degraded",
                message="Scheduler is not running",
            )
    except Exception as e:
        logger.error("scheduler_health_check_failed", error=str(e))
        return HealthStatus(
            status="unhealthy",
            message=f"Scheduler check failed: {str(e)[:100]}",
        )


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Health Check",
    description="Check the health status of the API and its dependencies.",
)
async def health_check(
    settings: Settings = Depends(get_settings),
) -> HealthCheckResponse:
    """
    Perform a comprehensive health check of all system components.

    Returns the status of:
    - Supabase (PostgreSQL database)
    - Neo4j (Knowledge graph)
    - Pinecone (Vector store)
    - Scheduler (APScheduler)
    """
    services = {}

    # Check all services
    services["supabase"] = await check_supabase_health(settings)
    services["neo4j"] = await check_neo4j_health(settings)
    services["pinecone"] = await check_pinecone_health(settings)
    services["scheduler"] = await check_scheduler_health()

    # Determine overall status
    statuses = [s.status for s in services.values()]
    if all(s == "healthy" for s in statuses):
        overall_status = "healthy"
    elif any(s == "unhealthy" for s in statuses):
        overall_status = "unhealthy"
    else:
        overall_status = "degraded"

    return HealthCheckResponse(
        status=overall_status,
        version="1.0.0",
        timestamp=datetime.now(timezone.utc),
        services=services,
        uptime_seconds=get_uptime_seconds(),
    )


@router.get(
    "/health/live",
    summary="Liveness Check",
    description="Simple liveness check for container orchestration.",
)
async def liveness() -> dict:
    """
    Simple liveness probe for Kubernetes/Cloud Run.

    Returns 200 if the service is alive.
    """
    return {"status": "alive", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get(
    "/health/ready",
    summary="Readiness Check",
    description="Check if the service is ready to accept traffic.",
)
async def readiness(
    settings: Settings = Depends(get_settings),
) -> dict:
    """
    Readiness probe for Kubernetes/Cloud Run.

    Returns 200 only if critical dependencies are available.
    """
    # Check critical services
    supabase_status = await check_supabase_health(settings)

    if supabase_status.status == "unhealthy":
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="Service not ready: database unavailable",
        )

    return {"status": "ready", "timestamp": datetime.now(timezone.utc).isoformat()}
