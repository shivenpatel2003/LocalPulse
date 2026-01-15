"""FastAPI dependency injection providers.

This module provides dependency functions for injecting services into route handlers.
"""

from typing import Optional

from supabase import create_client, Client

from src.config.settings import get_settings
from src.scheduler.scheduler import Scheduler

# Global instances for singleton pattern
_supabase_client: Optional[Client] = None
_scheduler_instance: Optional[Scheduler] = None


def get_supabase() -> Client:
    """
    Get Supabase client instance.

    Uses a singleton pattern to reuse the same client across requests.

    Returns:
        Authenticated Supabase client.
    """
    global _supabase_client

    if _supabase_client is None:
        settings = get_settings()
        _supabase_client = create_client(
            settings.supabase_url,
            settings.supabase_key.get_secret_value(),
        )

    return _supabase_client


def get_scheduler() -> Scheduler:
    """
    Get Scheduler instance.

    Returns the global scheduler instance that is initialized on startup.

    Returns:
        Scheduler instance.

    Raises:
        RuntimeError: If scheduler has not been initialized.
    """
    global _scheduler_instance

    if _scheduler_instance is None:
        raise RuntimeError(
            "Scheduler not initialized. Ensure the application startup event has run."
        )

    return _scheduler_instance


def set_scheduler(scheduler: Scheduler) -> None:
    """
    Set the global scheduler instance.

    Called during application startup to initialize the scheduler.

    Args:
        scheduler: Initialized Scheduler instance.
    """
    global _scheduler_instance
    _scheduler_instance = scheduler


def reset_dependencies() -> None:
    """
    Reset all global dependency instances.

    Useful for testing or application shutdown.
    """
    global _supabase_client, _scheduler_instance
    _supabase_client = None
    _scheduler_instance = None
