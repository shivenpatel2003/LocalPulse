"""Report endpoints for the LocalPulse API.

Provides endpoints for viewing and triggering report generation.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from supabase import Client

from src.api.models import (
    ReportSummary,
    ReportDetail,
    ReportRunRequest,
    ReportRunResponse,
    ReportHistoryResponse,
    ErrorResponse,
)
from src.api.dependencies import get_supabase, get_scheduler
from src.scheduler.scheduler import Scheduler
from src.graphs.master_graph import run_full_pipeline

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/reports", tags=["Reports"])

# In-memory cache for recent reports (in production, use Redis)
_report_cache: dict[str, dict] = {}


async def _get_client_or_404(client_id: UUID, supabase: Client) -> dict:
    """Get client data or raise 404."""
    result = supabase.table("scheduled_jobs").select("*").eq("client_id", str(client_id)).execute()

    if not result.data:
        raise HTTPException(
            status_code=404,
            detail=f"Client {client_id} not found",
        )

    return result.data[0]


async def _store_report(client_id: UUID, report_data: dict, supabase: Client) -> None:
    """Store report in database (reports table)."""
    try:
        # Check if reports table exists by attempting to insert
        report_record = {
            "id": str(uuid4()),
            "client_id": str(client_id),
            "business_name": report_data.get("business_name", "Unknown"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "success": report_data.get("success", False),
            "phase_completed": report_data.get("phase_completed", "unknown"),
            "duration_seconds": report_data.get("duration_seconds"),
            "collection_summary": report_data.get("collection_summary", {}),
            "analysis_summary": report_data.get("analysis_summary", {}),
            "report_summary": report_data.get("report_summary", {}),
            "errors": report_data.get("errors", []),
        }

        supabase.table("reports").insert(report_record).execute()
        logger.info("report_stored", client_id=str(client_id))

    except Exception as e:
        # Table might not exist yet, cache in memory
        logger.warning("report_storage_failed", error=str(e), client_id=str(client_id))
        _report_cache[str(client_id)] = {
            **report_data,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


@router.get(
    "/{client_id}",
    response_model=ReportDetail,
    summary="Get latest report",
    description="Retrieve the most recent report for a client.",
    responses={
        404: {"model": ErrorResponse, "description": "Client or report not found"},
    },
)
async def get_latest_report(
    client_id: UUID,
    supabase: Client = Depends(get_supabase),
) -> ReportDetail:
    """
    Get the most recent report for a client.

    Returns detailed information about the last generated report including
    collection data, analysis results, and any errors encountered.

    **Parameters:**
    - **client_id**: Unique identifier of the client
    """
    # Verify client exists
    client = await _get_client_or_404(client_id, supabase)

    try:
        # Try to get from reports table
        result = supabase.table("reports").select("*").eq(
            "client_id", str(client_id)
        ).order("generated_at", desc=True).limit(1).execute()

        if result.data:
            report = result.data[0]
            return ReportDetail(
                id=UUID(report["id"]),
                client_id=UUID(report["client_id"]),
                business_name=report["business_name"],
                generated_at=datetime.fromisoformat(report["generated_at"]),
                success=report.get("success", False),
                phase_completed=report.get("phase_completed", "unknown"),
                duration_seconds=report.get("duration_seconds"),
                collection_summary=report.get("collection_summary", {}),
                analysis_summary=report.get("analysis_summary", {}),
                report_summary=report.get("report_summary", {}),
                errors=report.get("errors", []),
            )

    except Exception as e:
        logger.warning("reports_table_query_failed", error=str(e))

    # Check in-memory cache
    if str(client_id) in _report_cache:
        cached = _report_cache[str(client_id)]
        return ReportDetail(
            id=uuid4(),
            client_id=client_id,
            business_name=cached.get("business_name", client["business_name"]),
            generated_at=datetime.fromisoformat(cached["generated_at"]) if cached.get("generated_at") else datetime.now(timezone.utc),
            success=cached.get("success", False),
            phase_completed=cached.get("phase_completed", "unknown"),
            duration_seconds=cached.get("duration_seconds"),
            collection_summary=cached.get("collection_summary", {}),
            analysis_summary=cached.get("analysis_summary", {}),
            report_summary=cached.get("report_summary", {}),
            errors=cached.get("errors", []),
        )

    # No report found, check if client has ever run
    if client.get("last_run"):
        raise HTTPException(
            status_code=404,
            detail=f"No report data available for client {client_id}. Last run was at {client['last_run']} but report data was not persisted.",
        )

    raise HTTPException(
        status_code=404,
        detail=f"No reports found for client {client_id}. Run a report first using POST /reports/{client_id}/run",
    )


@router.get(
    "/{client_id}/history",
    response_model=ReportHistoryResponse,
    summary="Get report history",
    description="Retrieve historical reports for a client.",
    responses={
        404: {"model": ErrorResponse, "description": "Client not found"},
    },
)
async def get_report_history(
    client_id: UUID,
    limit: int = Query(10, ge=1, le=100, description="Maximum number of reports"),
    offset: int = Query(0, ge=0, description="Number of reports to skip"),
    supabase: Client = Depends(get_supabase),
) -> ReportHistoryResponse:
    """
    Get historical reports for a client.

    Returns a list of past report summaries, ordered by generation date (newest first).

    **Parameters:**
    - **client_id**: Unique identifier of the client
    - **limit**: Maximum number of reports to return
    - **offset**: Number of reports to skip (for pagination)
    """
    # Verify client exists
    client = await _get_client_or_404(client_id, supabase)

    reports = []

    try:
        # Query reports table
        result = supabase.table("reports").select("*").eq(
            "client_id", str(client_id)
        ).order("generated_at", desc=True).range(offset, offset + limit - 1).execute()

        for report in (result.data or []):
            reports.append(ReportSummary(
                id=UUID(report["id"]),
                client_id=UUID(report["client_id"]),
                business_name=report["business_name"],
                generated_at=datetime.fromisoformat(report["generated_at"]),
                success=report.get("success", False),
                phase_completed=report.get("phase_completed", "unknown"),
                sentiment_score=report.get("analysis_summary", {}).get("sentiment_score"),
                insights_count=report.get("analysis_summary", {}).get("insights_count", 0),
                recommendations_count=report.get("analysis_summary", {}).get("recommendations_count", 0),
            ))

        # Get total count
        count_result = supabase.table("reports").select("id", count="exact").eq(
            "client_id", str(client_id)
        ).execute()
        total = count_result.count or len(reports)

    except Exception as e:
        logger.warning("reports_history_query_failed", error=str(e))
        total = 0

        # Include cached report if available
        if str(client_id) in _report_cache:
            cached = _report_cache[str(client_id)]
            reports.append(ReportSummary(
                id=uuid4(),
                client_id=client_id,
                business_name=cached.get("business_name", client["business_name"]),
                generated_at=datetime.fromisoformat(cached["generated_at"]) if cached.get("generated_at") else datetime.now(timezone.utc),
                success=cached.get("success", False),
                phase_completed=cached.get("phase_completed", "unknown"),
                sentiment_score=cached.get("analysis_summary", {}).get("sentiment_score"),
                insights_count=cached.get("analysis_summary", {}).get("insights_count", 0),
                recommendations_count=cached.get("analysis_summary", {}).get("recommendations_count", 0),
            ))
            total = 1

    return ReportHistoryResponse(reports=reports, total=total)


@router.post(
    "/{client_id}/run",
    response_model=ReportRunResponse,
    summary="Trigger report generation",
    description="Immediately generate a new report for a client.",
    responses={
        404: {"model": ErrorResponse, "description": "Client not found"},
        500: {"model": ErrorResponse, "description": "Report generation failed"},
    },
)
async def run_report(
    client_id: UUID,
    request: Optional[ReportRunRequest] = None,
    background_tasks: BackgroundTasks = None,
    supabase: Client = Depends(get_supabase),
    scheduler: Scheduler = Depends(get_scheduler),
) -> ReportRunResponse:
    """
    Trigger immediate report generation for a client.

    This runs the full LocalPulse pipeline:
    1. **Collection**: Gather data from Google Places API
    2. **Analysis**: AI-powered sentiment analysis, theme extraction, competitor comparison
    3. **Report**: Generate HTML report and optionally send via email

    The request is processed synchronously - the response will contain the full result.
    For large data sets, this may take 30-60 seconds.

    **Parameters:**
    - **client_id**: Unique identifier of the client
    - **send_email**: Whether to send the report via email (default: true)
    """
    # Verify client exists
    client = await _get_client_or_404(client_id, supabase)

    logger.info(
        "manual_report_triggered",
        client_id=str(client_id),
        business_name=client["business_name"],
    )

    try:
        # Run the pipeline
        result = await run_full_pipeline(
            business_name=client["business_name"],
            location=client.get("location", ""),
            owner_email=client["owner_email"] if (request is None or request.send_email) else None,
        )

        # Store the report
        await _store_report(client_id, result, supabase)

        # Update last_run in scheduled_jobs
        supabase.table("scheduled_jobs").update({
            "last_run": datetime.now(timezone.utc).isoformat(),
        }).eq("client_id", str(client_id)).execute()

        logger.info(
            "manual_report_complete",
            client_id=str(client_id),
            success=result.get("success", False),
        )

        return ReportRunResponse(
            success=result.get("success", False),
            business_name=result.get("business_name", client["business_name"]),
            phase_completed=result.get("phase_completed", "unknown"),
            duration_seconds=result.get("duration_seconds"),
            collection_summary=result.get("collection_summary", {}),
            analysis_summary=result.get("analysis_summary", {}),
            report_summary=result.get("report_summary", {}),
            errors=result.get("errors", []),
        )

    except Exception as e:
        logger.error(
            "manual_report_failed",
            client_id=str(client_id),
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Report generation failed: {str(e)}",
        )
