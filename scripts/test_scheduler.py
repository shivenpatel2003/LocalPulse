#!/usr/bin/env python3
"""CLI test script for the LocalPulse scheduler.

Usage:
    # Run basic scheduler tests (add, list, pause, resume, remove)
    python scripts/test_scheduler.py

    # Print SQL to create the Supabase table
    python scripts/test_scheduler.py sql

    # Trigger an immediate pipeline run for a test client
    python scripts/test_scheduler.py run

    # Add a new client
    python scripts/test_scheduler.py add "Restaurant Name" "Location" "email@example.com"

    # List all scheduled jobs
    python scripts/test_scheduler.py list

    # Remove a client by ID
    python scripts/test_scheduler.py remove <client_id>
"""

import asyncio
import sys
from uuid import UUID, uuid4

from src.scheduler.scheduler import (
    Scheduler,
    get_table_creation_sql,
    test_scheduler,
    test_immediate_run,
)


def print_usage():
    """Print usage instructions."""
    print(__doc__)


async def add_client(args: list[str]) -> None:
    """Add a new client to the scheduler."""
    if len(args) < 3:
        print("Usage: python scripts/test_scheduler.py add <business_name> <location> <email> [frequency] [day] [hour]")
        print("  frequency: daily, weekly, monthly (default: weekly)")
        print("  day: monday-sunday (default: monday)")
        print("  hour: 0-23 (default: 9)")
        return

    business_name = args[0]
    location = args[1]
    email = args[2]
    frequency = args[3] if len(args) > 3 else "weekly"
    day = args[4] if len(args) > 4 else "monday"
    hour = int(args[5]) if len(args) > 5 else 9

    scheduler = Scheduler()

    try:
        await scheduler.start()

        client_id = uuid4()
        job = await scheduler.schedule_client(
            client_id=client_id,
            business_name=business_name,
            location=location,
            email=email,
            frequency=frequency,
            day=day,
            hour=hour,
        )

        print(f"\nClient scheduled successfully!")
        print(f"  Client ID: {job.client_id}")
        print(f"  Business: {job.business_name}")
        print(f"  Location: {job.location}")
        print(f"  Email: {job.owner_email}")
        print(f"  Frequency: {job.frequency}")
        print(f"  Schedule Day: {job.schedule_day}")
        print(f"  Schedule Hour: {job.schedule_hour}")
        print(f"  Next Run: {job.next_run}")

    finally:
        await scheduler.stop()


async def list_clients() -> None:
    """List all scheduled clients."""
    scheduler = Scheduler()

    try:
        await scheduler.start()

        jobs = await scheduler.list_scheduled_jobs()

        if not jobs:
            print("\nNo scheduled jobs found.")
            return

        print(f"\nScheduled Jobs ({len(jobs)} total):")
        print("-" * 100)
        print(f"{'Client ID':<38} {'Business':<25} {'Freq':<8} {'Day':<10} {'Hour':<5} {'Active':<7} {'Next Run'}")
        print("-" * 100)

        for job in jobs:
            status = "Yes" if job.is_active else "No"
            next_run = job.next_run.strftime("%Y-%m-%d %H:%M") if job.next_run else "N/A"
            day = job.schedule_day or "N/A"
            print(f"{str(job.client_id):<38} {job.business_name[:24]:<25} {job.frequency:<8} {day:<10} {job.schedule_hour:<5} {status:<7} {next_run}")

        print("-" * 100)

    finally:
        await scheduler.stop()


async def remove_client(client_id_str: str) -> None:
    """Remove a client from the scheduler."""
    try:
        client_id = UUID(client_id_str)
    except ValueError:
        print(f"Invalid UUID: {client_id_str}")
        return

    scheduler = Scheduler()

    try:
        await scheduler.start()

        removed = await scheduler.remove_client(client_id)

        if removed:
            print(f"\nClient {client_id} removed successfully.")
        else:
            print(f"\nClient {client_id} not found.")

    finally:
        await scheduler.stop()


async def pause_client(client_id_str: str) -> None:
    """Pause a scheduled client."""
    try:
        client_id = UUID(client_id_str)
    except ValueError:
        print(f"Invalid UUID: {client_id_str}")
        return

    scheduler = Scheduler()

    try:
        await scheduler.start()

        paused = await scheduler.pause_client(client_id)

        if paused:
            print(f"\nClient {client_id} paused successfully.")
        else:
            print(f"\nClient {client_id} not found.")

    finally:
        await scheduler.stop()


async def resume_client(client_id_str: str) -> None:
    """Resume a paused client."""
    try:
        client_id = UUID(client_id_str)
    except ValueError:
        print(f"Invalid UUID: {client_id_str}")
        return

    scheduler = Scheduler()

    try:
        await scheduler.start()

        resumed = await scheduler.resume_client(client_id)

        if resumed:
            print(f"\nClient {client_id} resumed successfully.")
        else:
            print(f"\nClient {client_id} not found.")

    finally:
        await scheduler.stop()


async def run_client_now(client_id_str: str) -> None:
    """Trigger an immediate run for a client."""
    try:
        client_id = UUID(client_id_str)
    except ValueError:
        print(f"Invalid UUID: {client_id_str}")
        return

    scheduler = Scheduler()

    try:
        await scheduler.start()

        print(f"\nTriggering immediate run for client {client_id}...")
        result = await scheduler.run_now(client_id)

        print(f"\nResult:")
        print(f"  Success: {result.get('success')}")
        print(f"  Business: {result.get('business_name')}")
        print(f"  Phase: {result.get('phase_completed')}")
        print(f"  Duration: {result.get('duration_seconds', 0):.1f}s")

        if result.get('errors'):
            print(f"  Errors: {result.get('errors')}")

    except ValueError as e:
        print(f"\nError: {e}")
    finally:
        await scheduler.stop()


def main():
    """Main entry point for CLI."""
    if len(sys.argv) < 2:
        # Default: run basic tests
        asyncio.run(test_scheduler())
        return

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    if command == "help" or command == "-h" or command == "--help":
        print_usage()

    elif command == "sql":
        print("=" * 70)
        print("Supabase Table Creation SQL")
        print("=" * 70)
        print("\nRun this SQL in your Supabase SQL Editor:\n")
        print(get_table_creation_sql())
        print("=" * 70)

    elif command == "run":
        if args:
            # Run specific client
            asyncio.run(run_client_now(args[0]))
        else:
            # Run test client
            asyncio.run(test_immediate_run())

    elif command == "add":
        asyncio.run(add_client(args))

    elif command == "list":
        asyncio.run(list_clients())

    elif command == "remove":
        if not args:
            print("Usage: python scripts/test_scheduler.py remove <client_id>")
            return
        asyncio.run(remove_client(args[0]))

    elif command == "pause":
        if not args:
            print("Usage: python scripts/test_scheduler.py pause <client_id>")
            return
        asyncio.run(pause_client(args[0]))

    elif command == "resume":
        if not args:
            print("Usage: python scripts/test_scheduler.py resume <client_id>")
            return
        asyncio.run(resume_client(args[0]))

    elif command == "test":
        asyncio.run(test_scheduler())

    else:
        print(f"Unknown command: {command}")
        print_usage()


if __name__ == "__main__":
    main()
