"""
FastAPI Application.

This module contains the REST API for LocalPulse:

- main: FastAPI application entry point and configuration
- routes/: API endpoint definitions organized by domain
- middleware/: Authentication, logging, rate limiting, CORS

API Structure:
- /health - Health check and readiness probes
- /api/v1/businesses - Business CRUD operations
- /api/v1/reviews - Review queries and analysis
- /api/v1/insights - AI-generated insights
- /api/v1/alerts - Alert configuration and management
- /api/v1/reports - Report generation and retrieval

Example:
    from src.api.main import app

    # Run with: uvicorn src.api.main:app --reload
"""
