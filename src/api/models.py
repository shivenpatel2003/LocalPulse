"""Pydantic models for API requests and responses.

This module defines all the request/response schemas for the LocalPulse API.
"""

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, EmailStr


# =============================================================================
# Enums and Types
# =============================================================================

FrequencyType = Literal["daily", "weekly", "monthly"]
DayType = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# =============================================================================
# Client Models
# =============================================================================


class ClientCreate(BaseModel):
    """Request model for creating a new client."""

    business_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the business to monitor",
        json_schema_extra={"example": "Circolo Popolare"},
    )
    location: str = Field(
        ...,
        max_length=255,
        description="Location of the business",
        json_schema_extra={"example": "Manchester, UK"},
    )
    email: EmailStr = Field(
        ...,
        description="Email address for report delivery",
        json_schema_extra={"example": "owner@restaurant.com"},
    )
    frequency: FrequencyType = Field(
        default="weekly",
        description="How often to generate reports",
    )
    schedule_day: DayType = Field(
        default="monday",
        description="Day of week for weekly reports",
    )
    schedule_hour: int = Field(
        default=9,
        ge=0,
        le=23,
        description="Hour of day (0-23) to send reports",
    )


class ClientUpdate(BaseModel):
    """Request model for updating a client."""

    business_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Name of the business to monitor",
    )
    location: Optional[str] = Field(
        None,
        max_length=255,
        description="Location of the business",
    )
    email: Optional[EmailStr] = Field(
        None,
        description="Email address for report delivery",
    )
    frequency: Optional[FrequencyType] = Field(
        None,
        description="How often to generate reports",
    )
    schedule_day: Optional[DayType] = Field(
        None,
        description="Day of week for weekly reports",
    )
    schedule_hour: Optional[int] = Field(
        None,
        ge=0,
        le=23,
        description="Hour of day (0-23) to send reports",
    )


class ClientResponse(BaseModel):
    """Response model for a client."""

    id: UUID = Field(..., description="Unique client identifier")
    client_id: UUID = Field(..., description="Client ID used for scheduling")
    business_name: str = Field(..., description="Business name")
    location: str = Field(..., description="Business location")
    email: str = Field(..., description="Owner email")
    frequency: str = Field(..., description="Report frequency")
    schedule_day: Optional[str] = Field(None, description="Scheduled day")
    schedule_hour: int = Field(..., description="Scheduled hour")
    is_active: bool = Field(..., description="Whether scheduling is active")
    last_run: Optional[datetime] = Field(None, description="Last report run time")
    next_run: Optional[datetime] = Field(None, description="Next scheduled run time")
    created_at: Optional[datetime] = Field(None, description="When client was added")

    class Config:
        from_attributes = True


class ClientListResponse(BaseModel):
    """Response model for listing clients."""

    clients: list[ClientResponse] = Field(..., description="List of clients")
    total: int = Field(..., description="Total number of clients")


# =============================================================================
# Report Models
# =============================================================================


class ReportSummary(BaseModel):
    """Summary of a generated report."""

    id: UUID = Field(..., description="Report ID")
    client_id: UUID = Field(..., description="Client ID")
    business_name: str = Field(..., description="Business name")
    generated_at: datetime = Field(..., description="When report was generated")
    success: bool = Field(..., description="Whether report generation succeeded")
    phase_completed: str = Field(..., description="Last completed phase")
    sentiment_score: Optional[float] = Field(None, description="Overall sentiment score")
    insights_count: int = Field(default=0, description="Number of insights generated")
    recommendations_count: int = Field(default=0, description="Number of recommendations")


class ReportDetail(BaseModel):
    """Detailed report response."""

    id: UUID = Field(..., description="Report ID")
    client_id: UUID = Field(..., description="Client ID")
    business_name: str = Field(..., description="Business name")
    generated_at: datetime = Field(..., description="When report was generated")
    success: bool = Field(..., description="Whether report generation succeeded")
    phase_completed: str = Field(..., description="Last completed phase")
    duration_seconds: Optional[float] = Field(None, description="Pipeline duration")

    # Collection data
    collection_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Summary of collected data",
    )

    # Analysis data
    analysis_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Summary of analysis results",
    )

    # Report data
    report_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Summary of report generation",
    )

    # Full results (optional)
    report_html: Optional[str] = Field(None, description="Generated HTML report")
    insights: list[str] = Field(default_factory=list, description="Generated insights")
    recommendations: list[str] = Field(default_factory=list, description="Recommendations")
    errors: list[str] = Field(default_factory=list, description="Any errors encountered")


class ReportRunRequest(BaseModel):
    """Request to trigger an immediate report run."""

    send_email: bool = Field(
        default=True,
        description="Whether to send the report via email",
    )


class ReportRunResponse(BaseModel):
    """Response from triggering a report run."""

    success: bool = Field(..., description="Whether the run completed successfully")
    business_name: str = Field(..., description="Business name")
    phase_completed: str = Field(..., description="Last completed phase")
    duration_seconds: Optional[float] = Field(None, description="Pipeline duration")
    collection_summary: dict[str, Any] = Field(default_factory=dict)
    analysis_summary: dict[str, Any] = Field(default_factory=dict)
    report_summary: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class ReportHistoryResponse(BaseModel):
    """Response for report history."""

    reports: list[ReportSummary] = Field(..., description="List of past reports")
    total: int = Field(..., description="Total number of reports")


# =============================================================================
# Schedule Models
# =============================================================================


class ScheduleResponse(BaseModel):
    """Response model for a scheduled job."""

    id: UUID = Field(..., description="Schedule ID")
    client_id: UUID = Field(..., description="Client ID")
    business_name: str = Field(..., description="Business name")
    location: str = Field(..., description="Business location")
    email: str = Field(..., description="Owner email")
    frequency: str = Field(..., description="Schedule frequency")
    schedule_day: Optional[str] = Field(None, description="Day of week for weekly schedules")
    schedule_hour: int = Field(..., description="Hour of day (0-23)")
    is_active: bool = Field(..., description="Whether schedule is active")
    last_run: Optional[datetime] = Field(None, description="Last execution time")
    next_run: Optional[datetime] = Field(None, description="Next scheduled execution")
    created_at: Optional[datetime] = Field(None, description="When schedule was created")

    class Config:
        from_attributes = True


class ScheduleListResponse(BaseModel):
    """Response for listing schedules."""

    schedules: list[ScheduleResponse] = Field(..., description="List of schedules")
    total: int = Field(..., description="Total number of schedules")
    active_count: int = Field(..., description="Number of active schedules")
    paused_count: int = Field(..., description="Number of paused schedules")


class ScheduleActionResponse(BaseModel):
    """Response for schedule actions (pause/resume)."""

    success: bool = Field(..., description="Whether the action succeeded")
    client_id: UUID = Field(..., description="Client ID")
    action: str = Field(..., description="Action performed (paused/resumed)")
    is_active: bool = Field(..., description="Current active status")
    next_run: Optional[datetime] = Field(None, description="Next scheduled run (if active)")


# =============================================================================
# Health Check Models
# =============================================================================


class HealthStatus(BaseModel):
    """Individual service health status."""

    status: Literal["healthy", "unhealthy", "degraded"] = Field(
        ..., description="Service status"
    )
    latency_ms: Optional[float] = Field(None, description="Response latency in milliseconds")
    message: Optional[str] = Field(None, description="Additional status message")


class HealthCheckResponse(BaseModel):
    """Response model for health check endpoint."""

    status: Literal["healthy", "unhealthy", "degraded"] = Field(
        ..., description="Overall system status"
    )
    version: str = Field(..., description="API version")
    timestamp: datetime = Field(..., description="Check timestamp")
    services: dict[str, HealthStatus] = Field(
        default_factory=dict,
        description="Individual service statuses",
    )
    uptime_seconds: Optional[float] = Field(None, description="Server uptime in seconds")


# =============================================================================
# Error Models
# =============================================================================


class ErrorResponse(BaseModel):
    """Standard error response model."""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    detail: Optional[str] = Field(None, description="Additional error details")
    path: Optional[str] = Field(None, description="Request path that caused the error")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Error timestamp",
    )


class ValidationErrorDetail(BaseModel):
    """Details for validation errors."""

    field: str = Field(..., description="Field that failed validation")
    message: str = Field(..., description="Validation error message")
    value: Optional[Any] = Field(None, description="Invalid value provided")


class ValidationErrorResponse(BaseModel):
    """Response for validation errors."""

    error: str = Field(default="validation_error", description="Error type")
    message: str = Field(default="Request validation failed", description="Error message")
    errors: list[ValidationErrorDetail] = Field(..., description="List of validation errors")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")
