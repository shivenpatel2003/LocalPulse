"""Client management endpoints for the LocalPulse API.

Provides CRUD operations for managing monitored restaurant clients.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from src.api.models import (
    ClientCreate,
    ClientUpdate,
    ClientResponse,
    ClientListResponse,
    ErrorResponse,
)
from src.api.dependencies import get_supabase, get_scheduler
from src.scheduler.scheduler import Scheduler

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/clients", tags=["Clients"])


def _job_to_client_response(job_data: dict) -> ClientResponse:
    """Convert a scheduled job database row to a ClientResponse."""
    return ClientResponse(
        id=UUID(job_data["id"]),
        client_id=UUID(job_data["client_id"]),
        business_name=job_data["business_name"],
        location=job_data.get("location", ""),
        email=job_data["owner_email"],
        frequency=job_data["frequency"],
        schedule_day=job_data.get("schedule_day"),
        schedule_hour=job_data["schedule_hour"],
        is_active=job_data.get("is_active", True),
        last_run=datetime.fromisoformat(job_data["last_run"]) if job_data.get("last_run") else None,
        next_run=datetime.fromisoformat(job_data["next_run"]) if job_data.get("next_run") else None,
        created_at=datetime.fromisoformat(job_data["created_at"]) if job_data.get("created_at") else None,
    )


@router.post(
    "",
    response_model=ClientResponse,
    status_code=201,
    summary="Add a new client",
    description="Register a new restaurant client for monitoring and automated reports.",
    responses={
        201: {"description": "Client created successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request data"},
        409: {"model": ErrorResponse, "description": "Client already exists"},
    },
)
async def create_client(
    client: ClientCreate,
    supabase: Client = Depends(get_supabase),
    scheduler: Scheduler = Depends(get_scheduler),
) -> ClientResponse:
    """
    Create a new client for monitoring.

    This will:
    1. Create a new client record in the database
    2. Schedule automated report generation based on the specified frequency

    **Parameters:**
    - **business_name**: Name of the restaurant to monitor
    - **location**: Location (e.g., "Manchester, UK")
    - **email**: Email address for report delivery
    - **frequency**: How often to generate reports (daily, weekly, monthly)
    - **schedule_day**: Day of week for weekly reports
    - **schedule_hour**: Hour of day (0-23) to send reports
    """
    client_id = uuid4()

    logger.info(
        "creating_client",
        client_id=str(client_id),
        business_name=client.business_name,
    )

    try:
        # Schedule the client
        job = await scheduler.schedule_client(
            client_id=client_id,
            business_name=client.business_name,
            location=client.location,
            email=client.email,
            frequency=client.frequency,
            day=client.schedule_day,
            hour=client.schedule_hour,
        )

        logger.info(
            "client_created",
            client_id=str(client_id),
            business_name=client.business_name,
        )

        return ClientResponse(
            id=job.id,
            client_id=job.client_id,
            business_name=job.business_name,
            location=job.location,
            email=job.owner_email,
            frequency=job.frequency,
            schedule_day=job.schedule_day,
            schedule_hour=job.schedule_hour,
            is_active=job.is_active,
            last_run=job.last_run,
            next_run=job.next_run,
            created_at=job.created_at,
        )

    except ValueError as e:
        logger.warning("client_creation_conflict", error=str(e))
        raise HTTPException(
            status_code=409,
            detail=f"Client conflict: {str(e)}",
        )
    except Exception as e:
        logger.error("client_creation_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create client: {str(e)}",
        )


@router.get(
    "",
    response_model=ClientListResponse,
    summary="List all clients",
    description="Retrieve a list of all registered clients.",
)
async def list_clients(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    supabase: Client = Depends(get_supabase),
) -> ClientListResponse:
    """
    List all registered clients.

    Supports filtering by active status and pagination.
    """
    try:
        query = supabase.table("scheduled_jobs").select("*")

        if is_active is not None:
            query = query.eq("is_active", is_active)

        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
        result = query.execute()

        clients = [_job_to_client_response(job) for job in (result.data or [])]

        # Get total count
        count_query = supabase.table("scheduled_jobs").select("id", count="exact")
        if is_active is not None:
            count_query = count_query.eq("is_active", is_active)
        count_result = count_query.execute()
        total = count_result.count or len(clients)

        return ClientListResponse(clients=clients, total=total)

    except Exception as e:
        logger.error("list_clients_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list clients: {str(e)}",
        )


@router.get(
    "/{client_id}",
    response_model=ClientResponse,
    summary="Get client details",
    description="Retrieve details for a specific client.",
    responses={
        404: {"model": ErrorResponse, "description": "Client not found"},
    },
)
async def get_client(
    client_id: UUID,
    supabase: Client = Depends(get_supabase),
) -> ClientResponse:
    """
    Get detailed information about a specific client.

    **Parameters:**
    - **client_id**: Unique identifier of the client
    """
    try:
        result = supabase.table("scheduled_jobs").select("*").eq("client_id", str(client_id)).execute()

        if not result.data:
            raise HTTPException(
                status_code=404,
                detail=f"Client {client_id} not found",
            )

        return _job_to_client_response(result.data[0])

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_client_failed", client_id=str(client_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get client: {str(e)}",
        )


@router.put(
    "/{client_id}",
    response_model=ClientResponse,
    summary="Update client settings",
    description="Update settings for an existing client.",
    responses={
        404: {"model": ErrorResponse, "description": "Client not found"},
    },
)
async def update_client(
    client_id: UUID,
    update: ClientUpdate,
    supabase: Client = Depends(get_supabase),
    scheduler: Scheduler = Depends(get_scheduler),
) -> ClientResponse:
    """
    Update an existing client's settings.

    Only provided fields will be updated. To change scheduling settings,
    the client will be rescheduled with the new parameters.

    **Parameters:**
    - **client_id**: Unique identifier of the client
    - **update**: Fields to update
    """
    try:
        # Check client exists
        existing = supabase.table("scheduled_jobs").select("*").eq("client_id", str(client_id)).execute()

        if not existing.data:
            raise HTTPException(
                status_code=404,
                detail=f"Client {client_id} not found",
            )

        current = existing.data[0]

        # Build update data
        update_data = {}
        if update.business_name is not None:
            update_data["business_name"] = update.business_name
        if update.location is not None:
            update_data["location"] = update.location
        if update.email is not None:
            update_data["owner_email"] = update.email
        if update.frequency is not None:
            update_data["frequency"] = update.frequency
        if update.schedule_day is not None:
            update_data["schedule_day"] = update.schedule_day
        if update.schedule_hour is not None:
            update_data["schedule_hour"] = update.schedule_hour

        if not update_data:
            # No updates provided, return current state
            return _job_to_client_response(current)

        # Check if schedule needs to be recalculated
        schedule_changed = any(
            key in update_data
            for key in ["frequency", "schedule_day", "schedule_hour"]
        )

        if schedule_changed:
            # Recalculate next_run
            from src.scheduler.scheduler import ScheduledJob

            job = ScheduledJob.from_dict(current)
            if "frequency" in update_data:
                job.frequency = update_data["frequency"]
            if "schedule_day" in update_data:
                job.schedule_day = update_data["schedule_day"]
            if "schedule_hour" in update_data:
                job.schedule_hour = update_data["schedule_hour"]

            update_data["next_run"] = job.calculate_next_run().isoformat()

        # Update in database
        result = supabase.table("scheduled_jobs").update(update_data).eq("client_id", str(client_id)).execute()

        if not result.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to update client",
            )

        # If schedule changed and scheduler is running, update the job
        if schedule_changed and scheduler.is_running:
            from src.scheduler.scheduler import ScheduledJob

            updated_job = ScheduledJob.from_dict(result.data[0])
            scheduler._add_job_to_scheduler(updated_job)

        logger.info("client_updated", client_id=str(client_id), updates=list(update_data.keys()))

        return _job_to_client_response(result.data[0])

    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_client_failed", client_id=str(client_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update client: {str(e)}",
        )


@router.delete(
    "/{client_id}",
    status_code=204,
    summary="Remove client",
    description="Remove a client and cancel their scheduled reports.",
    responses={
        204: {"description": "Client removed successfully"},
        404: {"model": ErrorResponse, "description": "Client not found"},
    },
)
async def delete_client(
    client_id: UUID,
    scheduler: Scheduler = Depends(get_scheduler),
) -> None:
    """
    Remove a client and all associated scheduled jobs.

    This will:
    1. Cancel any scheduled report generation
    2. Remove the client from the database

    Note: This does not delete historical reports.

    **Parameters:**
    - **client_id**: Unique identifier of the client to remove
    """
    try:
        removed = await scheduler.remove_client(client_id)

        if not removed:
            raise HTTPException(
                status_code=404,
                detail=f"Client {client_id} not found",
            )

        logger.info("client_deleted", client_id=str(client_id))

    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_client_failed", client_id=str(client_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete client: {str(e)}",
        )
