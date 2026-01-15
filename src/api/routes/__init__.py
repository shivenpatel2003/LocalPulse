"""API route modules."""

from src.api.routes.health import router as health_router
from src.api.routes.clients import router as clients_router
from src.api.routes.reports import router as reports_router
from src.api.routes.schedules import router as schedules_router

__all__ = [
    "health_router",
    "clients_router",
    "reports_router",
    "schedules_router",
]
