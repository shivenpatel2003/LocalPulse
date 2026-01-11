"""
LocalPulse - Main Entry Point

AI-Powered Restaurant Monitoring & Competitive Intelligence Platform
"""

import asyncio
import sys
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events:
    - Initialize database connections
    - Start collector agents
    - Initialize knowledge graph
    - Graceful shutdown of all components
    """
    settings = get_settings()
    logger.info(
        "Starting LocalPulse",
        environment=settings.environment,
        version="0.1.0",
    )

    # TODO: Initialize Supabase connection
    # TODO: Initialize knowledge graph
    # TODO: Start background collector agents
    # TODO: Load long-term memory

    yield

    # Shutdown
    logger.info("Shutting down LocalPulse")
    # TODO: Graceful shutdown of collectors
    # TODO: Flush pending writes
    # TODO: Close database connections


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    settings = get_settings()

    app = FastAPI(
        title="LocalPulse API",
        description="AI-Powered Restaurant Monitoring & Competitive Intelligence",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_development else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint for monitoring."""
        return {
            "status": "healthy",
            "version": "0.1.0",
            "environment": settings.environment,
        }

    # API info endpoint
    @app.get("/")
    async def root():
        """Root endpoint with API information."""
        return {
            "name": "LocalPulse API",
            "version": "0.1.0",
            "description": "AI-Powered Restaurant Monitoring & Competitive Intelligence",
            "docs": "/docs" if settings.is_development else None,
        }

    # TODO: Include routers
    # app.include_router(businesses_router, prefix="/api/v1/businesses")
    # app.include_router(reviews_router, prefix="/api/v1/reviews")
    # app.include_router(analysis_router, prefix="/api/v1/analysis")
    # app.include_router(alerts_router, prefix="/api/v1/alerts")

    return app


# Create app instance
app = create_app()


def main():
    """Main entry point for running the application."""
    settings = get_settings()

    logger.info(
        "Starting server",
        host=settings.api_host,
        port=settings.api_port,
    )

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
