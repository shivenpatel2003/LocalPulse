"""LocalPulse API - Main FastAPI Application.

This module provides the main FastAPI application for the LocalPulse platform.
It includes:
- CORS middleware configuration
- API versioning (/api/v1)
- Health check endpoints
- Client, Report, and Schedule management endpoints
- Automatic scheduler initialization on startup

Usage:
    # Run with uvicorn
    uvicorn src.api.main:app --reload

    # Or run directly
    python -m src.api.main
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from src.api.dependencies import set_scheduler, reset_dependencies
from src.api.models import ErrorResponse, ValidationErrorResponse, ValidationErrorDetail
from src.api.routes.health import router as health_router, set_server_start_time
from src.api.routes.clients import router as clients_router
from src.api.routes.reports import router as reports_router
from src.api.routes.schedules import router as schedules_router
from src.config.settings import get_settings
from src.scheduler.scheduler import Scheduler

logger = structlog.get_logger(__name__)

# API metadata for OpenAPI documentation
API_TITLE = "LocalPulse API"
API_DESCRIPTION = """
## AI-Powered Restaurant Monitoring & Competitive Intelligence

LocalPulse is a platform that helps restaurant owners monitor their online presence,
track competitor activity, and receive actionable insights to improve their business.

### Features

- **Automated Monitoring**: Schedule daily, weekly, or monthly reports
- **Multi-Source Data Collection**: Google Places reviews, ratings, and business details
- **AI-Powered Analysis**: Sentiment analysis, theme extraction, and trend identification
- **Competitor Intelligence**: Track and compare against local competitors
- **Actionable Insights**: AI-generated recommendations for improvement

### Getting Started

1. **Add a Client**: Register a restaurant using `POST /api/v1/clients`
2. **Schedule Reports**: Configure automated report generation
3. **View Reports**: Access generated reports via `GET /api/v1/reports/{client_id}`
4. **Manage Schedules**: Pause, resume, or modify schedules as needed

### Authentication

Currently, the API does not require authentication. In production, implement
API key or OAuth2 authentication.
"""
API_VERSION = "1.0.0"

# CORS configuration
CORS_ORIGINS = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Handles startup and shutdown events:
    - Startup: Initialize database connections, start scheduler
    - Shutdown: Stop scheduler, cleanup resources
    """
    # Startup
    logger.info("application_starting")
    set_server_start_time()

    # Initialize scheduler
    scheduler = Scheduler()
    try:
        await scheduler.start()
        set_scheduler(scheduler)
        logger.info("scheduler_initialized")
    except Exception as e:
        logger.error("scheduler_initialization_failed", error=str(e))
        # Continue without scheduler - manual runs will still work
        set_scheduler(scheduler)

    logger.info("application_started")

    yield

    # Shutdown
    logger.info("application_stopping")

    try:
        if scheduler.is_running:
            await scheduler.stop()
            logger.info("scheduler_stopped")
    except Exception as e:
        logger.error("scheduler_shutdown_error", error=str(e))

    reset_dependencies()
    logger.info("application_stopped")


# Create FastAPI application
app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {
            "name": "Health",
            "description": "System health and status endpoints",
        },
        {
            "name": "Clients",
            "description": "Client management - add, update, and remove monitored restaurants",
        },
        {
            "name": "Reports",
            "description": "Report generation and retrieval",
        },
        {
            "name": "Schedules",
            "description": "Schedule management - pause, resume, and view scheduled jobs",
        },
    ],
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Exception Handlers
# =============================================================================


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors with detailed response."""
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        errors.append(ValidationErrorDetail(
            field=field,
            message=error["msg"],
            value=error.get("input"),
        ))

    response = ValidationErrorResponse(
        errors=errors,
        timestamp=datetime.now(timezone.utc),
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=response.model_dump(mode="json"),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Handle unexpected exceptions."""
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        error_type=type(exc).__name__,
    )

    response = ErrorResponse(
        error="internal_server_error",
        message="An unexpected error occurred",
        detail=str(exc) if get_settings().debug else None,
        path=request.url.path,
        timestamp=datetime.now(timezone.utc),
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response.model_dump(mode="json"),
    )


# =============================================================================
# Root Endpoints
# =============================================================================


@app.get("/", include_in_schema=False)
async def root() -> dict:
    """Root endpoint - redirects to API documentation."""
    return {
        "name": API_TITLE,
        "version": API_VERSION,
        "docs": "/docs",
        "health": "/health",
        "api": "/api/v1",
    }


# =============================================================================
# Include Routers
# =============================================================================

# Health endpoints at root level
app.include_router(health_router)

# Create API v1 router for versioned endpoints
from fastapi import APIRouter

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(clients_router)
api_v1_router.include_router(reports_router)
api_v1_router.include_router(schedules_router)

# Include the versioned router
app.include_router(api_v1_router)


# =============================================================================
# Additional Utility Endpoints
# =============================================================================


@app.get("/api/v1", include_in_schema=False)
async def api_v1_root() -> dict:
    """API v1 root - shows available endpoints."""
    return {
        "version": "v1",
        "endpoints": {
            "clients": "/api/v1/clients",
            "reports": "/api/v1/reports",
            "schedules": "/api/v1/schedules",
        },
        "documentation": "/docs",
    }


# =============================================================================
# Development Server
# =============================================================================


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )
