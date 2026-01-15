"""Schedule management endpoints for the LocalPulse API.

Provides endpoints for viewing and managing automated report schedules.
"""

from datetime import datetime, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from src.api.models import (
    ScheduleResponse,
    ScheduleListResponse,
    ScheduleActionResponse,
    ErrorResponse,
)
from src.api.dependencies import get_supabase, get_scheduler
from src.scheduler.scheduler import Scheduler

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/schedules", tags=["Schedules"])


def _job_to_schedule_response(job_data: dict) -> ScheduleResponse:
    """Convert a scheduled job database row to a ScheduleResponse."""
    return ScheduleResponse(
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


@router.get(
    "",
    response_model=ScheduleListResponse,
    summary="List all schedules",
    description="Retrieve a list of all scheduled report jobs.",
)
async def list_schedules(
    supabase: Client = Depends(get_supabase),
) -> ScheduleListResponse:
    """
    List all scheduled report generation jobs.

    Returns both active and paused schedules with their current status
    and next scheduled run time.
    """
    try:
        result = supabase.table("scheduled_jobs").select("*").order("created_at", desc=True).execute()

        schedules = [_job_to_schedule_response(job) for job in (result.data or [])]

        active_count = sum(1 for s in schedules if s.is_active)
        paused_count = len(schedules) - active_count

        return ScheduleListResponse(
            schedules=schedules,
            total=len(schedules),
            active_count=active_count,
            paused_count=paused_count,
        )

    except Exception as e:
        logger.error("list_schedules_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list schedules: {str(e)}",
        )


@router.get(
    "/{client_id}",
    response_model=ScheduleResponse,
    summary="Get schedule details",
    description="Retrieve schedule details for a specific client.",
    responses={
        404: {"model": ErrorResponse, "description": "Schedule not found"},
    },
)
async def get_schedule(
    client_id: UUID,
    supabase: Client = Depends(get_supabase),
) -> ScheduleResponse:
    """
    Get detailed schedule information for a specific client.

    **Parameters:**
    - **client_id**: Unique identifier of the client
    """
    try:
        result = supabase.table("scheduled_jobs").select("*").eq("client_id", str(client_id)).execute()

        if not result.data:
            raise HTTPException(
                status_code=404,
                detail=f"Schedule for client {client_id} not found",
            )

        return _job_to_schedule_response(result.data[0])

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_schedule_failed", client_id=str(client_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get schedule: {str(e)}",
        )


@router.put(
    "/{client_id}/pause",
    response_model=ScheduleActionResponse,
    summary="Pause schedule",
    description="Pause automated report generation for a client.",
    responses={
        404: {"model": ErrorResponse, "description": "Schedule not found"},
    },
)
async def pause_schedule(
    client_id: UUID,
    scheduler: Scheduler = Depends(get_scheduler),
    supabase: Client = Depends(get_supabase),
) -> ScheduleActionResponse:
    """
    Pause scheduled report generation for a client.

    The schedule remains in the database but will not execute until resumed.
    Manual report generation via POST /reports/{client_id}/run is still available.

    **Parameters:**
    - **client_id**: Unique identifier of the client
    """
    try:
        paused = await scheduler.pause_client(client_id)

        if not paused:
            raise HTTPException(
                status_code=404,
                detail=f"Schedule for client {client_id} not found",
            )

        logger.info("schedule_paused", client_id=str(client_id))

        return ScheduleActionResponse(
            success=True,
            client_id=client_id,
            action="paused",
            is_active=False,
            next_run=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("pause_schedule_failed", client_id=str(client_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to pause schedule: {str(e)}",
        )


@router.put(
    "/{client_id}/resume",
    response_model=ScheduleActionResponse,
    summary="Resume schedule",
    description="Resume automated report generation for a paused client.",
    responses={
        404: {"model": ErrorResponse, "description": "Schedule not found"},
    },
)
async def resume_schedule(
    client_id: UUID,
    scheduler: Scheduler = Depends(get_scheduler),
    supabase: Client = Depends(get_supabase),
) -> ScheduleActionResponse:
    """
    Resume scheduled report generation for a paused client.

    The schedule will be reactivated and the next run time will be calculated
    based on the configured frequency and schedule settings.

    **Parameters:**
    - **client_id**: Unique identifier of the client
    """
    try:
        resumed = await scheduler.resume_client(client_id)

        if not resumed:
            raise HTTPException(
                status_code=404,
                detail=f"Schedule for client {client_id} not found",
            )

        # Get updated schedule info
        result = supabase.table("scheduled_jobs").select("next_run").eq("client_id", str(client_id)).execute()
        next_run = None
        if result.data and result.data[0].get("next_run"):
            next_run = datetime.fromisoformat(result.data[0]["next_run"])

        logger.info("schedule_resumed", client_id=str(client_id), next_run=str(next_run))

        return ScheduleActionResponse(
            success=True,
            client_id=client_id,
            action="resumed",
            is_active=True,
            next_run=next_run,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("resume_schedule_failed", client_id=str(client_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resume schedule: {str(e)}",
        )


@router.get(
    "/status/summary",
    summary="Get schedule status summary",
    description="Get a summary of all schedule statuses.",
)
async def get_schedule_summary(
    supabase: Client = Depends(get_supabase),
) -> dict:
    """
    Get a summary of schedule statuses.

    Returns counts of active, paused, and overdue schedules.
    """
    try:
        result = supabase.table("scheduled_jobs").select("*").execute()
        jobs = result.data or []

        now = datetime.now(timezone.utc)
        active = 0
        paused = 0
        overdue = 0
        upcoming_24h = 0

        for job in jobs:
            if job.get("is_active"):
                active += 1
                if job.get("next_run"):
                    next_run = datetime.fromisoformat(job["next_run"])
                    if next_run < now:
                        overdue += 1
                    elif (next_run - now).total_seconds() < 86400:
                        upcoming_24h += 1
            else:
                paused += 1

        return {
            "total": len(jobs),
            "active": active,
            "paused": paused,
            "overdue": overdue,
            "upcoming_24h": upcoming_24h,
            "timestamp": now.isoformat(),
        }

    except Exception as e:
        logger.error("get_schedule_summary_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get schedule summary: {str(e)}",
        )
