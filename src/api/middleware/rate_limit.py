"""Rate limiting middleware for FastAPI.

Applies rate limiting to incoming API requests using the configured rate limiter
(Redis-backed or in-memory fallback).

Usage:
    from src.api.middleware import RateLimitMiddleware

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

The middleware will automatically use the global rate limiter instance.
Health, docs, and metrics endpoints are excluded from rate limiting.
"""

from typing import Optional

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.core.rate_limiter import get_rate_limiter, RateLimitResult

logger = structlog.get_logger(__name__)


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after:.1f} seconds.")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to apply rate limiting to API requests.

    Features:
    - Uses Redis-backed rate limiter when available
    - Falls back to in-memory when Redis unavailable
    - Skips rate limiting for health, docs, and metrics endpoints
    - Returns 429 with Retry-After header when limit exceeded
    - Adds X-RateLimit-Remaining header to responses
    """

    # Endpoints excluded from rate limiting (monitoring and documentation)
    EXCLUDED_PATHS = {
        "/",
        "/health",
        "/health/live",
        "/health/ready",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/metrics",
    }

    # Rate limit configuration: 100 requests per minute per client
    DEFAULT_LIMIT = 100
    DEFAULT_WINDOW = 60  # seconds

    def __init__(
        self,
        app: ASGIApp,
        limit: int = DEFAULT_LIMIT,
        window: int = DEFAULT_WINDOW,
    ):
        """
        Initialize rate limit middleware.

        Args:
            app: The ASGI application
            limit: Maximum requests allowed in window (default: 100)
            window: Time window in seconds (default: 60)
        """
        super().__init__(app)
        self.limit = limit
        self.window = window
        self._limiter_initialized = False

    def _get_client_identifier(self, request: Request) -> str:
        """
        Get unique identifier for the client.

        Uses X-Forwarded-For header if behind proxy, otherwise uses client host.
        Prefixes with "api_requests:" for the rate limiter key.
        """
        # Check for forwarded header (when behind proxy/load balancer)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take the first IP in the chain (original client)
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        return f"api_requests:{client_ip}"

    async def dispatch(self, request: Request, call_next):
        """Process request through rate limiting."""
        # Skip rate limiting for excluded paths
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        # Get rate limiter (lazy initialization)
        try:
            limiter = await get_rate_limiter()
        except Exception as e:
            logger.warning(
                "rate_limiter_unavailable",
                error=str(e),
                message="Proceeding without rate limiting",
            )
            return await call_next(request)

        # Get client identifier for rate limiting
        identifier = self._get_client_identifier(request)

        try:
            # Check rate limit
            result: RateLimitResult = await limiter.is_allowed(
                identifier=identifier,
                limit=self.limit,
                window=self.window,
            )

            if not result.allowed:
                # Rate limit exceeded
                logger.warning(
                    "rate_limit_exceeded",
                    client=identifier,
                    path=request.url.path,
                    retry_after=result.retry_after,
                )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "rate_limit_exceeded",
                        "message": "Too many requests. Please slow down.",
                        "retry_after": round(result.retry_after, 1) if result.retry_after else self.window,
                    },
                    headers={
                        "Retry-After": str(int(result.retry_after or self.window)),
                        "X-RateLimit-Limit": str(self.limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(result.reset_at)),
                    },
                )

            # Request allowed - proceed with rate limit headers
            response = await call_next(request)

            # Add rate limit headers to response
            response.headers["X-RateLimit-Limit"] = str(self.limit)
            response.headers["X-RateLimit-Remaining"] = str(result.remaining)
            response.headers["X-RateLimit-Reset"] = str(int(result.reset_at))

            return response

        except Exception as e:
            # If rate limiting fails, allow the request through
            logger.error(
                "rate_limit_check_failed",
                error=str(e),
                client=identifier,
                message="Allowing request due to rate limit error",
            )
            return await call_next(request)
