"""Scheduler for automated LocalPulse pipeline runs.

This module provides a scheduling system that:
- Uses APScheduler for job scheduling
- Stores job definitions in Supabase for persistence across restarts
- Integrates with the master pipeline for automated report generation

Supabase Table Schema (scheduled_jobs):
    - id: UUID (primary key)
    - client_id: UUID (unique identifier for the client)
    - business_name: str
    - location: str
    - owner_email: str
    - frequency: str (daily, weekly, monthly)
    - schedule_day: str (monday, tuesday, etc. for weekly)
    - schedule_hour: int (0-23)
    - is_active: bool
    - last_run: datetime
    - next_run: datetime
    - created_at: datetime
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from supabase import create_client, Client

from src.config.settings import get_settings
from src.graphs.master_graph import run_full_pipeline

logger = structlog.get_logger(__name__)

# Day name to cron day mapping
DAY_TO_CRON = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

FrequencyType = Literal["daily", "weekly", "monthly"]
DayType = Literal[
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
]


# =============================================================================
# Supabase Table Initialization
# =============================================================================

SCHEDULED_JOBS_TABLE_SQL = """
-- ============================================================================
-- LocalPulse Database Schema
-- Run this SQL in Supabase SQL Editor to create the required tables
-- ============================================================================

-- -----------------------------------------------------------------------------
-- Scheduled Jobs Table
-- Stores client scheduling information for automated report generation
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID UNIQUE NOT NULL,
    business_name TEXT NOT NULL,
    location TEXT DEFAULT '',
    owner_email TEXT NOT NULL,
    frequency TEXT NOT NULL CHECK (frequency IN ('daily', 'weekly', 'monthly')),
    schedule_day TEXT CHECK (schedule_day IN ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')),
    schedule_hour INTEGER NOT NULL CHECK (schedule_hour >= 0 AND schedule_hour <= 23),
    is_active BOOLEAN DEFAULT true,
    last_run TIMESTAMPTZ,
    next_run TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for scheduled_jobs
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_client_id ON scheduled_jobs(client_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_is_active ON scheduled_jobs(is_active);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next_run ON scheduled_jobs(next_run);

-- -----------------------------------------------------------------------------
-- Reports Table
-- Stores generated report data for historical access
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES scheduled_jobs(client_id) ON DELETE CASCADE,
    business_name TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    success BOOLEAN DEFAULT false,
    phase_completed TEXT,
    duration_seconds FLOAT,
    collection_summary JSONB DEFAULT '{}',
    analysis_summary JSONB DEFAULT '{}',
    report_summary JSONB DEFAULT '{}',
    report_html TEXT,
    insights JSONB DEFAULT '[]',
    recommendations JSONB DEFAULT '[]',
    errors JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for reports
CREATE INDEX IF NOT EXISTS idx_reports_client_id ON reports(client_id);
CREATE INDEX IF NOT EXISTS idx_reports_generated_at ON reports(generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_reports_success ON reports(success);

-- -----------------------------------------------------------------------------
-- Updated At Trigger Function
-- Automatically updates the updated_at timestamp on row modification
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to scheduled_jobs
DROP TRIGGER IF EXISTS update_scheduled_jobs_updated_at ON scheduled_jobs;
CREATE TRIGGER update_scheduled_jobs_updated_at
    BEFORE UPDATE ON scheduled_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Row Level Security (optional, enable if needed)
-- ALTER TABLE scheduled_jobs ENABLE ROW LEVEL SECURITY;
"""


def get_table_creation_sql() -> str:
    """Get the SQL statement to create the scheduled_jobs table.

    Returns:
        SQL string to create the table. Run this in Supabase SQL Editor.
    """
    return SCHEDULED_JOBS_TABLE_SQL


async def initialize_supabase_table(supabase_client: Client) -> bool:
    """Check if the scheduled_jobs table exists and is accessible.

    Note: Supabase doesn't allow direct DDL through the client API.
    You must run the SQL from get_table_creation_sql() in the Supabase
    SQL Editor to create the table.

    Args:
        supabase_client: Authenticated Supabase client.

    Returns:
        True if table is accessible, False otherwise.
    """
    try:
        # Try to query the table to verify it exists
        result = supabase_client.table("scheduled_jobs").select("id").limit(1).execute()
        logger.info("supabase_table_check", status="accessible")
        return True
    except Exception as e:
        logger.error(
            "supabase_table_check_failed",
            error=str(e),
            hint="Run get_table_creation_sql() in Supabase SQL Editor to create the table",
        )
        return False


# =============================================================================
# Job Data Model
# =============================================================================


class ScheduledJob:
    """Represents a scheduled job for a client."""

    def __init__(
        self,
        client_id: UUID,
        business_name: str,
        location: str,
        owner_email: str,
        frequency: FrequencyType,
        schedule_day: Optional[DayType],
        schedule_hour: int,
        is_active: bool = True,
        last_run: Optional[datetime] = None,
        next_run: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
        id: Optional[UUID] = None,
    ):
        self.id = id or uuid4()
        self.client_id = client_id
        self.business_name = business_name
        self.location = location
        self.owner_email = owner_email
        self.frequency = frequency
        self.schedule_day = schedule_day
        self.schedule_hour = schedule_hour
        self.is_active = is_active
        self.last_run = last_run
        self.next_run = next_run
        self.created_at = created_at or datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Supabase storage."""
        return {
            "id": str(self.id),
            "client_id": str(self.client_id),
            "business_name": self.business_name,
            "location": self.location,
            "owner_email": self.owner_email,
            "frequency": self.frequency,
            "schedule_day": self.schedule_day,
            "schedule_hour": self.schedule_hour,
            "is_active": self.is_active,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScheduledJob":
        """Create ScheduledJob from Supabase response."""
        return cls(
            id=UUID(data["id"]) if data.get("id") else None,
            client_id=UUID(data["client_id"]),
            business_name=data["business_name"],
            location=data.get("location", ""),
            owner_email=data["owner_email"],
            frequency=data["frequency"],
            schedule_day=data.get("schedule_day"),
            schedule_hour=data["schedule_hour"],
            is_active=data.get("is_active", True),
            last_run=datetime.fromisoformat(data["last_run"]) if data.get("last_run") else None,
            next_run=datetime.fromisoformat(data["next_run"]) if data.get("next_run") else None,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
        )

    def get_cron_trigger(self) -> CronTrigger:
        """Get APScheduler CronTrigger for this job's schedule."""
        if self.frequency == "daily":
            return CronTrigger(hour=self.schedule_hour, minute=0)
        elif self.frequency == "weekly":
            day_of_week = DAY_TO_CRON.get(self.schedule_day, 0)
            return CronTrigger(
                day_of_week=day_of_week,
                hour=self.schedule_hour,
                minute=0,
            )
        elif self.frequency == "monthly":
            return CronTrigger(
                day=1,  # First day of month
                hour=self.schedule_hour,
                minute=0,
            )
        else:
            raise ValueError(f"Unknown frequency: {self.frequency}")

    def calculate_next_run(self) -> datetime:
        """Calculate the next run time based on schedule."""
        now = datetime.now(timezone.utc)

        if self.frequency == "daily":
            # Next occurrence at schedule_hour
            next_run = now.replace(hour=self.schedule_hour, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run

        elif self.frequency == "weekly":
            # Next occurrence on schedule_day at schedule_hour
            target_day = DAY_TO_CRON.get(self.schedule_day, 0)
            current_day = now.weekday()
            days_ahead = target_day - current_day
            if days_ahead < 0 or (days_ahead == 0 and now.hour >= self.schedule_hour):
                days_ahead += 7
            next_run = now + timedelta(days=days_ahead)
            next_run = next_run.replace(hour=self.schedule_hour, minute=0, second=0, microsecond=0)
            return next_run

        elif self.frequency == "monthly":
            # Next occurrence on 1st of month at schedule_hour
            if now.day == 1 and now.hour < self.schedule_hour:
                next_run = now.replace(hour=self.schedule_hour, minute=0, second=0, microsecond=0)
            else:
                # Move to first of next month
                if now.month == 12:
                    next_run = now.replace(year=now.year + 1, month=1, day=1)
                else:
                    next_run = now.replace(month=now.month + 1, day=1)
                next_run = next_run.replace(hour=self.schedule_hour, minute=0, second=0, microsecond=0)
            return next_run

        return now


# =============================================================================
# Scheduler Class
# =============================================================================


class Scheduler:
    """Scheduler for automated LocalPulse pipeline runs.

    Uses APScheduler for job scheduling and Supabase for persistent storage.
    Jobs survive application restarts by being stored in Supabase.

    Example:
        scheduler = Scheduler()
        await scheduler.start()

        # Add a client
        job = await scheduler.schedule_client(
            client_id=uuid4(),
            business_name="My Restaurant",
            location="London, UK",
            email="owner@example.com",
            frequency="weekly",
            day="monday",
            hour=9,
        )

        # List all jobs
        jobs = await scheduler.list_scheduled_jobs()

        # Trigger immediate run
        await scheduler.run_now(client_id)

        # Stop scheduler
        await scheduler.stop()
    """

    def __init__(self, supabase_url: Optional[str] = None, supabase_key: Optional[str] = None):
        """Initialize the scheduler.

        Args:
            supabase_url: Supabase project URL. Defaults to settings.
            supabase_key: Supabase API key. Defaults to settings.
        """
        settings = get_settings()
        self._supabase_url = supabase_url or settings.supabase_url
        self._supabase_key = supabase_key or settings.supabase_key.get_secret_value()

        self._supabase: Optional[Client] = None
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._is_running = False

        logger.info("scheduler_initialized")

    @property
    def is_running(self) -> bool:
        """Check if the scheduler is currently running."""
        return self._is_running

    def _get_supabase(self) -> Client:
        """Get or create Supabase client."""
        if self._supabase is None:
            self._supabase = create_client(self._supabase_url, self._supabase_key)
        return self._supabase

    async def start(self) -> None:
        """Start the scheduler and load all active jobs from Supabase."""
        if self._is_running:
            logger.warning("scheduler_already_running")
            return

        logger.info("scheduler_starting")

        # Verify Supabase table exists
        supabase = self._get_supabase()
        table_ok = await initialize_supabase_table(supabase)
        if not table_ok:
            logger.error(
                "scheduler_start_failed",
                reason="Supabase table not accessible",
            )
            raise RuntimeError(
                "scheduled_jobs table not found. "
                "Run get_table_creation_sql() in Supabase SQL Editor to create it."
            )

        # Create and start APScheduler
        self._scheduler = AsyncIOScheduler()
        self._scheduler.start()

        # Load all active jobs from Supabase
        await self._load_jobs_from_supabase()

        self._is_running = True
        logger.info("scheduler_started")

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if not self._is_running:
            logger.warning("scheduler_not_running")
            return

        logger.info("scheduler_stopping")

        if self._scheduler:
            self._scheduler.shutdown(wait=True)
            self._scheduler = None

        self._is_running = False
        logger.info("scheduler_stopped")

    async def _load_jobs_from_supabase(self) -> None:
        """Load all active jobs from Supabase and add them to the scheduler."""
        supabase = self._get_supabase()

        try:
            result = supabase.table("scheduled_jobs").select("*").eq("is_active", True).execute()
            jobs = result.data or []

            logger.info("loading_jobs_from_supabase", count=len(jobs))

            for job_data in jobs:
                job = ScheduledJob.from_dict(job_data)
                self._add_job_to_scheduler(job)

            logger.info("jobs_loaded", count=len(jobs))

        except Exception as e:
            logger.error("load_jobs_failed", error=str(e))
            raise

    def _add_job_to_scheduler(self, job: ScheduledJob) -> None:
        """Add a job to the APScheduler."""
        if not self._scheduler:
            logger.warning("scheduler_not_started")
            return

        job_id = f"job_{job.client_id}"

        # Remove existing job if present
        existing = self._scheduler.get_job(job_id)
        if existing:
            self._scheduler.remove_job(job_id)

        # Add job with cron trigger
        trigger = job.get_cron_trigger()
        self._scheduler.add_job(
            self._execute_job,
            trigger=trigger,
            id=job_id,
            args=[job],
            name=f"LocalPulse: {job.business_name}",
            replace_existing=True,
        )

        logger.info(
            "job_added_to_scheduler",
            client_id=str(job.client_id),
            business_name=job.business_name,
            frequency=job.frequency,
            schedule_day=job.schedule_day,
            schedule_hour=job.schedule_hour,
        )

    async def _execute_job(self, job: ScheduledJob) -> None:
        """
        Execute the pipeline for a scheduled job.

        Includes timeout protection and proper exception re-raising for APScheduler retry.
        """
        settings = get_settings()
        timeout_seconds = settings.pipeline_timeout_seconds

        logger.info(
            "job_execution_start",
            client_id=str(job.client_id),
            business_name=job.business_name,
            timeout_seconds=timeout_seconds,
        )

        try:
            # Run the full pipeline with timeout protection
            async with asyncio.timeout(timeout_seconds):
                result = await run_full_pipeline(
                    business_name=job.business_name,
                    location=job.location,
                    owner_email=job.owner_email,
                )

            # Update last_run and next_run in Supabase
            now = datetime.now(timezone.utc)
            job.last_run = now
            job.next_run = job.calculate_next_run()

            await self._update_job_run_times(job)

            logger.info(
                "job_execution_complete",
                client_id=str(job.client_id),
                business_name=job.business_name,
                success=result.get("success", False),
                next_run=job.next_run.isoformat(),
            )

        except asyncio.TimeoutError:
            logger.error(
                "job_execution_timeout",
                client_id=str(job.client_id),
                business_name=job.business_name,
                timeout_seconds=timeout_seconds,
            )
            # Re-raise so APScheduler knows job failed and can retry
            raise

        except Exception as e:
            logger.error(
                "job_execution_failed",
                client_id=str(job.client_id),
                business_name=job.business_name,
                error=str(e),
                error_type=type(e).__name__,
            )
            # Re-raise so APScheduler knows job failed and can retry per policy
            raise

    async def _update_job_run_times(self, job: ScheduledJob) -> None:
        """Update last_run and next_run in Supabase."""
        supabase = self._get_supabase()

        try:
            supabase.table("scheduled_jobs").update({
                "last_run": job.last_run.isoformat() if job.last_run else None,
                "next_run": job.next_run.isoformat() if job.next_run else None,
            }).eq("client_id", str(job.client_id)).execute()

        except Exception as e:
            logger.error("update_run_times_failed", error=str(e))

    async def schedule_client(
        self,
        client_id: UUID,
        business_name: str,
        location: str,
        email: str,
        frequency: FrequencyType = "weekly",
        day: DayType = "monday",
        hour: int = 9,
    ) -> ScheduledJob:
        """Schedule a new client for automated pipeline runs.

        Args:
            client_id: Unique identifier for the client.
            business_name: Name of the business to monitor.
            location: Location of the business (e.g., "London, UK").
            email: Email address for report delivery.
            frequency: Run frequency - "daily", "weekly", or "monthly".
            day: Day of week for weekly schedules.
            hour: Hour of day (0-23) to run the pipeline.

        Returns:
            The created ScheduledJob.

        Raises:
            ValueError: If a job already exists for this client_id.
        """
        supabase = self._get_supabase()

        # Check if client already exists
        existing = supabase.table("scheduled_jobs").select("id").eq("client_id", str(client_id)).execute()
        if existing.data:
            raise ValueError(f"Client {client_id} already has a scheduled job")

        # Create job
        job = ScheduledJob(
            client_id=client_id,
            business_name=business_name,
            location=location,
            owner_email=email,
            frequency=frequency,
            schedule_day=day if frequency == "weekly" else None,
            schedule_hour=hour,
            is_active=True,
        )
        job.next_run = job.calculate_next_run()

        # Save to Supabase
        try:
            supabase.table("scheduled_jobs").insert(job.to_dict()).execute()
            logger.info(
                "client_scheduled",
                client_id=str(client_id),
                business_name=business_name,
                frequency=frequency,
                next_run=job.next_run.isoformat(),
            )
        except Exception as e:
            logger.error("schedule_client_failed", error=str(e))
            raise

        # Add to scheduler if running
        if self._is_running:
            self._add_job_to_scheduler(job)

        return job

    async def remove_client(self, client_id: UUID) -> bool:
        """Remove a scheduled client.

        Args:
            client_id: The client's unique identifier.

        Returns:
            True if removed, False if not found.
        """
        supabase = self._get_supabase()

        try:
            result = supabase.table("scheduled_jobs").delete().eq("client_id", str(client_id)).execute()

            if not result.data:
                logger.warning("remove_client_not_found", client_id=str(client_id))
                return False

            # Remove from scheduler
            if self._scheduler:
                job_id = f"job_{client_id}"
                job = self._scheduler.get_job(job_id)
                if job:
                    self._scheduler.remove_job(job_id)

            logger.info("client_removed", client_id=str(client_id))
            return True

        except Exception as e:
            logger.error("remove_client_failed", error=str(e))
            raise

    async def list_scheduled_jobs(self) -> list[ScheduledJob]:
        """List all scheduled jobs.

        Returns:
            List of all scheduled jobs (active and inactive).
        """
        supabase = self._get_supabase()

        try:
            result = supabase.table("scheduled_jobs").select("*").order("created_at").execute()
            jobs = [ScheduledJob.from_dict(data) for data in (result.data or [])]

            logger.info("list_jobs", count=len(jobs))
            return jobs

        except Exception as e:
            logger.error("list_jobs_failed", error=str(e))
            raise

    async def run_now(self, client_id: UUID) -> dict[str, Any]:
        """Trigger an immediate pipeline run for a client.

        Args:
            client_id: The client's unique identifier.

        Returns:
            Pipeline result dictionary.

        Raises:
            ValueError: If client not found.
        """
        supabase = self._get_supabase()

        # Get job from Supabase
        result = supabase.table("scheduled_jobs").select("*").eq("client_id", str(client_id)).execute()

        if not result.data:
            raise ValueError(f"Client {client_id} not found")

        job = ScheduledJob.from_dict(result.data[0])

        logger.info(
            "manual_run_triggered",
            client_id=str(client_id),
            business_name=job.business_name,
        )

        # Run the pipeline
        pipeline_result = await run_full_pipeline(
            business_name=job.business_name,
            location=job.location,
            owner_email=job.owner_email,
        )

        # Update last_run
        job.last_run = datetime.now(timezone.utc)
        job.next_run = job.calculate_next_run()
        await self._update_job_run_times(job)

        return pipeline_result

    async def pause_client(self, client_id: UUID) -> bool:
        """Pause scheduled runs for a client.

        The job remains in the database but won't be executed.

        Args:
            client_id: The client's unique identifier.

        Returns:
            True if paused, False if not found.
        """
        supabase = self._get_supabase()

        try:
            result = supabase.table("scheduled_jobs").update({
                "is_active": False,
            }).eq("client_id", str(client_id)).execute()

            if not result.data:
                logger.warning("pause_client_not_found", client_id=str(client_id))
                return False

            # Remove from scheduler
            if self._scheduler:
                job_id = f"job_{client_id}"
                job = self._scheduler.get_job(job_id)
                if job:
                    self._scheduler.remove_job(job_id)

            logger.info("client_paused", client_id=str(client_id))
            return True

        except Exception as e:
            logger.error("pause_client_failed", error=str(e))
            raise

    async def resume_client(self, client_id: UUID) -> bool:
        """Resume scheduled runs for a paused client.

        Args:
            client_id: The client's unique identifier.

        Returns:
            True if resumed, False if not found.
        """
        supabase = self._get_supabase()

        try:
            # Get job data
            result = supabase.table("scheduled_jobs").select("*").eq("client_id", str(client_id)).execute()

            if not result.data:
                logger.warning("resume_client_not_found", client_id=str(client_id))
                return False

            job = ScheduledJob.from_dict(result.data[0])

            # Update next_run and activate
            job.next_run = job.calculate_next_run()
            supabase.table("scheduled_jobs").update({
                "is_active": True,
                "next_run": job.next_run.isoformat(),
            }).eq("client_id", str(client_id)).execute()

            # Add back to scheduler
            if self._is_running:
                self._add_job_to_scheduler(job)

            logger.info("client_resumed", client_id=str(client_id))
            return True

        except Exception as e:
            logger.error("resume_client_failed", error=str(e))
            raise

    async def get_job(self, client_id: UUID) -> Optional[ScheduledJob]:
        """Get a specific scheduled job by client ID.

        Args:
            client_id: The client's unique identifier.

        Returns:
            ScheduledJob if found, None otherwise.
        """
        supabase = self._get_supabase()

        try:
            result = supabase.table("scheduled_jobs").select("*").eq("client_id", str(client_id)).execute()

            if not result.data:
                return None

            return ScheduledJob.from_dict(result.data[0])

        except Exception as e:
            logger.error("get_job_failed", error=str(e))
            raise


# =============================================================================
# CLI Test Functions
# =============================================================================


async def test_scheduler():
    """Test the scheduler with basic operations."""
    print("=" * 70)
    print("LocalPulse Scheduler Test")
    print("=" * 70)

    scheduler = Scheduler()

    try:
        # Start the scheduler
        print("\n1. Starting scheduler...")
        await scheduler.start()
        print("   Scheduler started successfully!")

        # List existing jobs
        print("\n2. Listing existing jobs...")
        jobs = await scheduler.list_scheduled_jobs()
        print(f"   Found {len(jobs)} existing job(s)")
        for job in jobs:
            print(f"   - {job.business_name} ({job.frequency}, active={job.is_active})")

        # Add a test client
        print("\n3. Adding test client...")
        test_client_id = uuid4()
        try:
            job = await scheduler.schedule_client(
                client_id=test_client_id,
                business_name="Test Restaurant",
                location="Manchester, UK",
                email="test@example.com",
                frequency="weekly",
                day="monday",
                hour=9,
            )
            print(f"   Added: {job.business_name}")
            print(f"   Client ID: {job.client_id}")
            print(f"   Next run: {job.next_run}")
        except ValueError as e:
            print(f"   Note: {e}")

        # List jobs again
        print("\n4. Listing all jobs after addition...")
        jobs = await scheduler.list_scheduled_jobs()
        print(f"   Total jobs: {len(jobs)}")
        for job in jobs:
            status = "active" if job.is_active else "paused"
            next_run = job.next_run.strftime("%Y-%m-%d %H:%M") if job.next_run else "N/A"
            print(f"   - {job.business_name}: {job.frequency}, {status}, next: {next_run}")

        # Pause the test client
        print("\n5. Pausing test client...")
        paused = await scheduler.pause_client(test_client_id)
        print(f"   Paused: {paused}")

        # Resume the test client
        print("\n6. Resuming test client...")
        resumed = await scheduler.resume_client(test_client_id)
        print(f"   Resumed: {resumed}")

        # Remove the test client
        print("\n7. Removing test client...")
        removed = await scheduler.remove_client(test_client_id)
        print(f"   Removed: {removed}")

        # Final job count
        print("\n8. Final job list...")
        jobs = await scheduler.list_scheduled_jobs()
        print(f"   Total jobs: {len(jobs)}")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Stop the scheduler
        print("\n9. Stopping scheduler...")
        await scheduler.stop()
        print("   Scheduler stopped.")

    print("\n" + "=" * 70)
    print("Test completed!")
    print("=" * 70)


async def test_immediate_run():
    """Test triggering an immediate run for a client."""
    print("=" * 70)
    print("LocalPulse Immediate Run Test")
    print("=" * 70)

    scheduler = Scheduler()

    try:
        await scheduler.start()

        # Add a test client
        test_client_id = uuid4()
        job = await scheduler.schedule_client(
            client_id=test_client_id,
            business_name="Circolo Popolare Manchester",
            location="Manchester, UK",
            email="test@example.com",
            frequency="weekly",
            day="monday",
            hour=9,
        )

        print(f"\nTriggering immediate run for: {job.business_name}")
        print("-" * 50)

        # Trigger immediate run
        result = await scheduler.run_now(test_client_id)

        print(f"\nResult:")
        print(f"  Success: {result.get('success')}")
        print(f"  Phase: {result.get('phase_completed')}")
        print(f"  Duration: {result.get('duration_seconds', 0):.1f}s")

        # Cleanup
        await scheduler.remove_client(test_client_id)

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await scheduler.stop()

    print("\n" + "=" * 70)


def print_table_sql():
    """Print the SQL required to create the scheduled_jobs table."""
    print("=" * 70)
    print("Supabase Table Creation SQL")
    print("=" * 70)
    print("\nRun this SQL in your Supabase SQL Editor:\n")
    print(get_table_creation_sql())
    print("=" * 70)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "run":
            # Test immediate run
            asyncio.run(test_immediate_run())
        elif command == "sql":
            # Print table SQL
            print_table_sql()
        else:
            print(f"Unknown command: {command}")
            print("Usage: python -m src.scheduler.scheduler [run|sql]")
    else:
        # Default: run basic tests
        asyncio.run(test_scheduler())
