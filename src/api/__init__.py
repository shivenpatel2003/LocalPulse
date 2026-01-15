"""
LocalPulse FastAPI Application.

This module contains the REST API for LocalPulse:

- main: FastAPI application entry point and configuration
- routes/: API endpoint definitions organized by domain
- models: Pydantic request/response models
- dependencies: FastAPI dependency injection providers

API Structure:
- /health - Health check and readiness probes
- /api/v1/clients - Client management (add, update, remove)
- /api/v1/reports - Report generation and retrieval
- /api/v1/schedules - Schedule management (pause, resume, view)

Example:
    from src.api.main import app

    # Run with: uvicorn src.api.main:app --reload
"""

from src.api.main import app

__all__ = ["app"]
