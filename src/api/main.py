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
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.dependencies import set_scheduler, reset_dependencies
from src.api.models import ErrorResponse, ValidationErrorResponse, ValidationErrorDetail
from src.api.routes.health import router as health_router, set_server_start_time
from src.api.routes.clients import router as clients_router
from src.api.routes.reports import router as reports_router
from src.api.routes.schedules import router as schedules_router
from src.api.routes.onboarding import router as onboarding_router
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

API key authentication is available. Set `API_KEY_ENABLED=true` and `API_KEY=your-secret-key`
in environment to require X-API-Key header on all requests.
"""
API_VERSION = "1.0.0"


# =============================================================================
# API Key Authentication Middleware
# =============================================================================


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Middleware to validate API key for all requests except health/docs endpoints.

    Enable by setting API_KEY_ENABLED=true and API_KEY=<secret> in environment.
    """

    # Endpoints that don't require authentication
    PUBLIC_PATHS = {"/", "/health", "/health/live", "/health/ready", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()

        # Skip auth if disabled
        if not settings.api_key_enabled:
            return await call_next(request)

        # Skip auth for public paths
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)

        # Validate API key
        api_key = request.headers.get("X-API-Key")
        expected_key = settings.api_key.get_secret_value() if settings.api_key else None

        if not expected_key:
            logger.error("api_key_enabled_but_not_set")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "Server misconfiguration: API key authentication enabled but no key configured"},
            )

        if not api_key:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Missing X-API-Key header"},
            )

        if api_key != expected_key:
            logger.warning("invalid_api_key_attempt", path=request.url.path)
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Invalid API key"},
            )

        return await call_next(request)


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
        {
            "name": "Onboarding",
            "description": "AI-powered configuration generation - describe your business and get a custom monitoring setup",
        },
    ],
)

# Configure CORS middleware (from settings)
_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_allowed_origins,
    allow_credentials=_settings.cors_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "Accept"],
)

# Add API Key authentication middleware
app.add_middleware(APIKeyMiddleware)


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
api_v1_router.include_router(onboarding_router)

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
            "onboarding": "/api/v1/onboard",
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
