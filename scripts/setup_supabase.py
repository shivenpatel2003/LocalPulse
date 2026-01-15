#!/usr/bin/env python3
"""Supabase database setup script for LocalPulse.

This script outputs the SQL needed to create all required tables in Supabase.
Copy the SQL output and run it in the Supabase SQL Editor.

Usage:
    # Print all SQL to console
    python scripts/setup_supabase.py

    # Print SQL and save to file
    python scripts/setup_supabase.py --output setup.sql

    # Verify tables exist
    python scripts/setup_supabase.py --verify

Tables Created:
    - clients: Restaurant client information
    - scheduled_jobs: Report scheduling configuration
    - reports: Generated report storage
    - run_history: Pipeline execution history
    - onboarding_sessions: AI onboarding conversation sessions
    - industry_configs: Generated industry configurations
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

# =============================================================================
# SQL Schema Definitions
# =============================================================================

SCHEMA_SQL = """
-- =============================================================================
-- LocalPulse Database Schema for Supabase
-- =============================================================================
-- Generated: {generated_at}
--
-- Instructions:
-- 1. Open your Supabase project dashboard
-- 2. Go to SQL Editor
-- 3. Paste this entire script
-- 4. Click "Run" to execute
-- =============================================================================

-- Enable UUID extension (should already be enabled in Supabase)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- Table: clients
-- =============================================================================
-- Stores information about restaurant clients being monitored.
-- This is the primary table for client management.
-- =============================================================================

CREATE TABLE IF NOT EXISTS clients (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Business information
    business_name TEXT NOT NULL,
    google_place_id TEXT,
    location TEXT DEFAULT '',

    -- Owner contact
    owner_email TEXT NOT NULL,

    -- Status
    is_active BOOLEAN DEFAULT true,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT clients_business_name_not_empty CHECK (business_name <> ''),
    CONSTRAINT clients_owner_email_not_empty CHECK (owner_email <> '')
);

-- Indexes for clients table
CREATE INDEX IF NOT EXISTS idx_clients_business_name ON clients(business_name);
CREATE INDEX IF NOT EXISTS idx_clients_google_place_id ON clients(google_place_id);
CREATE INDEX IF NOT EXISTS idx_clients_owner_email ON clients(owner_email);
CREATE INDEX IF NOT EXISTS idx_clients_is_active ON clients(is_active);
CREATE INDEX IF NOT EXISTS idx_clients_created_at ON clients(created_at DESC);

-- Comments
COMMENT ON TABLE clients IS 'Restaurant clients being monitored by LocalPulse';
COMMENT ON COLUMN clients.id IS 'Unique identifier for the client';
COMMENT ON COLUMN clients.business_name IS 'Name of the restaurant/business';
COMMENT ON COLUMN clients.google_place_id IS 'Google Places API ID for data collection';
COMMENT ON COLUMN clients.location IS 'Business location (city, area)';
COMMENT ON COLUMN clients.owner_email IS 'Email address for report delivery';
COMMENT ON COLUMN clients.is_active IS 'Whether the client is actively monitored';


-- =============================================================================
-- Table: scheduled_jobs
-- =============================================================================
-- Stores scheduling configuration for automated report generation.
-- Links to clients table via client_id.
-- =============================================================================

CREATE TABLE IF NOT EXISTS scheduled_jobs (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Foreign key to clients
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    -- Schedule configuration
    frequency TEXT NOT NULL DEFAULT 'weekly',
    schedule_day TEXT DEFAULT 'monday',
    schedule_hour INTEGER NOT NULL DEFAULT 9,

    -- Status
    is_active BOOLEAN DEFAULT true,

    -- Execution tracking
    last_run TIMESTAMPTZ,
    next_run TIMESTAMPTZ,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT scheduled_jobs_frequency_valid CHECK (frequency IN ('daily', 'weekly', 'monthly')),
    CONSTRAINT scheduled_jobs_schedule_day_valid CHECK (
        schedule_day IS NULL OR
        schedule_day IN ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')
    ),
    CONSTRAINT scheduled_jobs_schedule_hour_valid CHECK (schedule_hour >= 0 AND schedule_hour <= 23),
    CONSTRAINT scheduled_jobs_client_unique UNIQUE (client_id)
);

-- Indexes for scheduled_jobs table
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_client_id ON scheduled_jobs(client_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_is_active ON scheduled_jobs(is_active);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next_run ON scheduled_jobs(next_run);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_frequency ON scheduled_jobs(frequency);

-- Comments
COMMENT ON TABLE scheduled_jobs IS 'Scheduling configuration for automated report generation';
COMMENT ON COLUMN scheduled_jobs.frequency IS 'Report frequency: daily, weekly, or monthly';
COMMENT ON COLUMN scheduled_jobs.schedule_day IS 'Day of week for weekly schedules';
COMMENT ON COLUMN scheduled_jobs.schedule_hour IS 'Hour of day (0-23) to run the pipeline';
COMMENT ON COLUMN scheduled_jobs.last_run IS 'Timestamp of last successful execution';
COMMENT ON COLUMN scheduled_jobs.next_run IS 'Timestamp of next scheduled execution';


-- =============================================================================
-- Table: reports
-- =============================================================================
-- Stores generated reports for historical access and analytics.
-- Links to clients table via client_id.
-- =============================================================================

CREATE TABLE IF NOT EXISTS reports (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Foreign key to clients
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    -- Report timing
    report_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    period_start TIMESTAMPTZ,
    period_end TIMESTAMPTZ,

    -- Report content
    report_html TEXT,
    report_data JSONB DEFAULT '{{}}',

    -- Metadata
    success BOOLEAN DEFAULT false,
    phase_completed TEXT,
    duration_seconds FLOAT,

    -- Analysis summaries (denormalized for quick access)
    sentiment_score FLOAT,
    review_count INTEGER,
    insights_count INTEGER,
    recommendations_count INTEGER,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT reports_sentiment_score_valid CHECK (sentiment_score IS NULL OR (sentiment_score >= -1 AND sentiment_score <= 1)),
    CONSTRAINT reports_review_count_valid CHECK (review_count IS NULL OR review_count >= 0)
);

-- Indexes for reports table
CREATE INDEX IF NOT EXISTS idx_reports_client_id ON reports(client_id);
CREATE INDEX IF NOT EXISTS idx_reports_report_date ON reports(report_date DESC);
CREATE INDEX IF NOT EXISTS idx_reports_success ON reports(success);
CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at DESC);

-- Composite index for common query pattern
CREATE INDEX IF NOT EXISTS idx_reports_client_date ON reports(client_id, report_date DESC);

-- Comments
COMMENT ON TABLE reports IS 'Generated intelligence reports for clients';
COMMENT ON COLUMN reports.report_date IS 'Date the report was generated';
COMMENT ON COLUMN reports.period_start IS 'Start of the analysis period';
COMMENT ON COLUMN reports.period_end IS 'End of the analysis period';
COMMENT ON COLUMN reports.report_html IS 'Generated HTML report content';
COMMENT ON COLUMN reports.report_data IS 'Structured report data as JSON';
COMMENT ON COLUMN reports.phase_completed IS 'Last pipeline phase completed';


-- =============================================================================
-- Table: run_history
-- =============================================================================
-- Tracks all pipeline execution attempts for monitoring and debugging.
-- Links to clients table via client_id.
-- =============================================================================

CREATE TABLE IF NOT EXISTS run_history (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Foreign key to clients
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    -- Execution timing
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    -- Status tracking
    status TEXT NOT NULL DEFAULT 'running',
    error_message TEXT,

    -- Phase tracking
    phases_completed JSONB DEFAULT '[]',

    -- Performance metrics
    duration_seconds FLOAT,

    -- Additional metadata
    trigger_type TEXT DEFAULT 'scheduled',
    metadata JSONB DEFAULT '{{}}',

    -- Constraints
    CONSTRAINT run_history_status_valid CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    CONSTRAINT run_history_trigger_type_valid CHECK (trigger_type IN ('scheduled', 'manual', 'retry'))
);

-- Indexes for run_history table
CREATE INDEX IF NOT EXISTS idx_run_history_client_id ON run_history(client_id);
CREATE INDEX IF NOT EXISTS idx_run_history_started_at ON run_history(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_run_history_status ON run_history(status);
CREATE INDEX IF NOT EXISTS idx_run_history_trigger_type ON run_history(trigger_type);

-- Composite index for client run history queries
CREATE INDEX IF NOT EXISTS idx_run_history_client_started ON run_history(client_id, started_at DESC);

-- Comments
COMMENT ON TABLE run_history IS 'Pipeline execution history for monitoring and debugging';
COMMENT ON COLUMN run_history.status IS 'Execution status: running, completed, failed, cancelled';
COMMENT ON COLUMN run_history.phases_completed IS 'Array of completed pipeline phases';
COMMENT ON COLUMN run_history.trigger_type IS 'What triggered the run: scheduled, manual, retry';
COMMENT ON COLUMN run_history.metadata IS 'Additional execution metadata';


-- =============================================================================
-- Updated At Trigger Function
-- =============================================================================
-- Automatically updates the updated_at timestamp on row modification.
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to clients table
DROP TRIGGER IF EXISTS update_clients_updated_at ON clients;
CREATE TRIGGER update_clients_updated_at
    BEFORE UPDATE ON clients
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Apply trigger to scheduled_jobs table
DROP TRIGGER IF EXISTS update_scheduled_jobs_updated_at ON scheduled_jobs;
CREATE TRIGGER update_scheduled_jobs_updated_at
    BEFORE UPDATE ON scheduled_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- =============================================================================
-- Table: onboarding_sessions
-- =============================================================================
-- Stores AI onboarding conversation sessions for configuration generation.
-- These are temporary sessions that capture the conversation flow.
-- =============================================================================

CREATE TABLE IF NOT EXISTS onboarding_sessions (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Conversation data
    conversation_history JSONB DEFAULT '[]',

    -- Generated configuration (stored as JSONB)
    current_config JSONB,

    -- Session status
    status TEXT NOT NULL DEFAULT 'needs_more_info',

    -- Clarifying questions (if any)
    questions JSONB DEFAULT '[]',

    -- AI reasoning for configuration choices
    generation_reasoning TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT onboarding_sessions_status_valid CHECK (
        status IN ('needs_more_info', 'config_ready', 'confirmed', 'error')
    )
);

-- Indexes for onboarding_sessions
CREATE INDEX IF NOT EXISTS idx_onboarding_sessions_status ON onboarding_sessions(status);
CREATE INDEX IF NOT EXISTS idx_onboarding_sessions_created_at ON onboarding_sessions(created_at DESC);

-- Comments
COMMENT ON TABLE onboarding_sessions IS 'AI onboarding conversation sessions';
COMMENT ON COLUMN onboarding_sessions.conversation_history IS 'Array of conversation messages';
COMMENT ON COLUMN onboarding_sessions.current_config IS 'Generated IndustryConfig as JSON';
COMMENT ON COLUMN onboarding_sessions.status IS 'Session status: needs_more_info, config_ready, confirmed, error';
COMMENT ON COLUMN onboarding_sessions.questions IS 'Clarifying questions asked by AI';
COMMENT ON COLUMN onboarding_sessions.generation_reasoning IS 'AI explanation of configuration choices';


-- =============================================================================
-- Table: industry_configs
-- =============================================================================
-- Stores generated industry configurations for clients.
-- Each client can have one active configuration that defines their monitoring.
-- =============================================================================

CREATE TABLE IF NOT EXISTS industry_configs (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Foreign key to clients
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    -- The complete configuration stored as JSONB
    config_data JSONB NOT NULL,

    -- Original user description that generated this config
    source_description TEXT,

    -- Config status
    status TEXT NOT NULL DEFAULT 'active',

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT industry_configs_status_valid CHECK (status IN ('active', 'inactive', 'archived')),
    CONSTRAINT industry_configs_client_unique UNIQUE (client_id)
);

-- Indexes for industry_configs
CREATE INDEX IF NOT EXISTS idx_industry_configs_client_id ON industry_configs(client_id);
CREATE INDEX IF NOT EXISTS idx_industry_configs_status ON industry_configs(status);
CREATE INDEX IF NOT EXISTS idx_industry_configs_created_at ON industry_configs(created_at DESC);

-- GIN index for JSONB queries on config_data
CREATE INDEX IF NOT EXISTS idx_industry_configs_config_data ON industry_configs USING gin(config_data);

-- Comments
COMMENT ON TABLE industry_configs IS 'Generated industry configurations for clients';
COMMENT ON COLUMN industry_configs.config_data IS 'Complete IndustryConfig as JSON';
COMMENT ON COLUMN industry_configs.source_description IS 'Original user input that generated this config';
COMMENT ON COLUMN industry_configs.status IS 'Config status: active, inactive, archived';

-- Apply updated_at trigger to new tables
DROP TRIGGER IF EXISTS update_onboarding_sessions_updated_at ON onboarding_sessions;
CREATE TRIGGER update_onboarding_sessions_updated_at
    BEFORE UPDATE ON onboarding_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_industry_configs_updated_at ON industry_configs;
CREATE TRIGGER update_industry_configs_updated_at
    BEFORE UPDATE ON industry_configs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- =============================================================================
-- Utility Functions
-- =============================================================================

-- Function to get client with their schedule
CREATE OR REPLACE FUNCTION get_client_with_schedule(p_client_id UUID)
RETURNS TABLE (
    client_id UUID,
    business_name TEXT,
    location TEXT,
    owner_email TEXT,
    is_active BOOLEAN,
    frequency TEXT,
    schedule_day TEXT,
    schedule_hour INTEGER,
    last_run TIMESTAMPTZ,
    next_run TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id AS client_id,
        c.business_name,
        c.location,
        c.owner_email,
        c.is_active,
        s.frequency,
        s.schedule_day,
        s.schedule_hour,
        s.last_run,
        s.next_run
    FROM clients c
    LEFT JOIN scheduled_jobs s ON s.client_id = c.id
    WHERE c.id = p_client_id;
END;
$$ LANGUAGE plpgsql;

-- Function to get recent run history for a client
CREATE OR REPLACE FUNCTION get_client_run_history(p_client_id UUID, p_limit INTEGER DEFAULT 10)
RETURNS TABLE (
    run_id UUID,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    status TEXT,
    duration_seconds FLOAT,
    trigger_type TEXT,
    error_message TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        r.id AS run_id,
        r.started_at,
        r.completed_at,
        r.status,
        r.duration_seconds,
        r.trigger_type,
        r.error_message
    FROM run_history r
    WHERE r.client_id = p_client_id
    ORDER BY r.started_at DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- Function to get dashboard summary
CREATE OR REPLACE FUNCTION get_dashboard_summary()
RETURNS TABLE (
    total_clients BIGINT,
    active_clients BIGINT,
    total_reports BIGINT,
    successful_runs BIGINT,
    failed_runs BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        (SELECT COUNT(*) FROM clients) AS total_clients,
        (SELECT COUNT(*) FROM clients WHERE is_active = true) AS active_clients,
        (SELECT COUNT(*) FROM reports) AS total_reports,
        (SELECT COUNT(*) FROM run_history WHERE status = 'completed') AS successful_runs,
        (SELECT COUNT(*) FROM run_history WHERE status = 'failed') AS failed_runs;
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- Row Level Security (RLS) - Disabled for now
-- =============================================================================
-- Uncomment these lines to enable RLS when needed.
-- You'll need to create policies based on your authentication strategy.
-- =============================================================================

-- ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE scheduled_jobs ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE run_history ENABLE ROW LEVEL SECURITY;

-- Example policy (uncomment and customize when implementing auth):
-- CREATE POLICY "Enable read access for authenticated users" ON clients
--     FOR SELECT USING (auth.role() = 'authenticated');


-- =============================================================================
-- Sample Data (Optional - Uncomment to insert test data)
-- =============================================================================

-- INSERT INTO clients (business_name, location, owner_email) VALUES
--     ('Circolo Popolare', 'Manchester, UK', 'test@example.com');

-- INSERT INTO scheduled_jobs (client_id, frequency, schedule_day, schedule_hour)
-- SELECT id, 'weekly', 'monday', 9 FROM clients WHERE business_name = 'Circolo Popolare';


-- =============================================================================
-- Verification Query
-- =============================================================================
-- Run this to verify all tables were created successfully:
-- =============================================================================

SELECT
    table_name,
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name) as column_count
FROM information_schema.tables t
WHERE table_schema = 'public'
    AND table_name IN ('clients', 'scheduled_jobs', 'reports', 'run_history', 'onboarding_sessions', 'industry_configs')
ORDER BY table_name;

-- =============================================================================
-- Setup Complete!
-- =============================================================================
"""


# =============================================================================
# Migration SQL (for updating existing schema)
# =============================================================================

MIGRATION_SQL = """
-- =============================================================================
-- Migration Script: Update Existing Schema
-- =============================================================================
-- Use this if you have existing tables and need to add new columns/constraints.
-- =============================================================================

-- Add new columns to clients if they don't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'clients' AND column_name = 'google_place_id') THEN
        ALTER TABLE clients ADD COLUMN google_place_id TEXT;
    END IF;
END $$;

-- Add new columns to reports if they don't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'reports' AND column_name = 'sentiment_score') THEN
        ALTER TABLE reports ADD COLUMN sentiment_score FLOAT;
        ALTER TABLE reports ADD COLUMN review_count INTEGER;
        ALTER TABLE reports ADD COLUMN insights_count INTEGER;
        ALTER TABLE reports ADD COLUMN recommendations_count INTEGER;
    END IF;
END $$;

-- Create run_history table if it doesn't exist
CREATE TABLE IF NOT EXISTS run_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running',
    error_message TEXT,
    phases_completed JSONB DEFAULT '[]',
    duration_seconds FLOAT,
    trigger_type TEXT DEFAULT 'scheduled',
    metadata JSONB DEFAULT '{{}}',
    CONSTRAINT run_history_status_valid CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    CONSTRAINT run_history_trigger_type_valid CHECK (trigger_type IN ('scheduled', 'manual', 'retry'))
);

-- Create missing indexes
CREATE INDEX IF NOT EXISTS idx_run_history_client_id ON run_history(client_id);
CREATE INDEX IF NOT EXISTS idx_run_history_started_at ON run_history(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_run_history_status ON run_history(status);
"""


# =============================================================================
# Drop Tables SQL (use with caution!)
# =============================================================================

DROP_TABLES_SQL = """
-- =============================================================================
-- DROP ALL TABLES (USE WITH EXTREME CAUTION!)
-- =============================================================================
-- This will delete ALL data. Only use for complete reset during development.
-- =============================================================================

-- Drop tables in correct order (respecting foreign key constraints)
DROP TABLE IF EXISTS onboarding_sessions CASCADE;
DROP TABLE IF EXISTS industry_configs CASCADE;
DROP TABLE IF EXISTS run_history CASCADE;
DROP TABLE IF EXISTS reports CASCADE;
DROP TABLE IF EXISTS scheduled_jobs CASCADE;
DROP TABLE IF EXISTS clients CASCADE;

-- Drop functions
DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;
DROP FUNCTION IF EXISTS get_client_with_schedule(UUID) CASCADE;
DROP FUNCTION IF EXISTS get_client_run_history(UUID, INTEGER) CASCADE;
DROP FUNCTION IF EXISTS get_dashboard_summary() CASCADE;
"""


# =============================================================================
# Verification Functions
# =============================================================================

async def verify_tables() -> dict:
    """Verify that all required tables exist in Supabase.

    Returns:
        Dictionary with verification results.
    """
    try:
        from supabase import create_client
        from src.config.settings import get_settings

        settings = get_settings()
        supabase = create_client(
            settings.supabase_url,
            settings.supabase_key.get_secret_value(),
        )

        required_tables = ['clients', 'scheduled_jobs', 'reports', 'run_history', 'onboarding_sessions', 'industry_configs']
        results = {
            'success': True,
            'tables': {},
            'missing': [],
            'errors': [],
        }

        for table in required_tables:
            try:
                # Try to query the table
                response = supabase.table(table).select('id').limit(1).execute()
                results['tables'][table] = {
                    'exists': True,
                    'accessible': True,
                    'row_count': len(response.data) if response.data else 0,
                }
            except Exception as e:
                error_str = str(e)
                if 'does not exist' in error_str.lower() or 'relation' in error_str.lower():
                    results['tables'][table] = {
                        'exists': False,
                        'accessible': False,
                    }
                    results['missing'].append(table)
                    results['success'] = False
                else:
                    results['tables'][table] = {
                        'exists': 'unknown',
                        'accessible': False,
                        'error': error_str[:100],
                    }
                    results['errors'].append(f"{table}: {error_str[:100]}")

        return results

    except ImportError:
        return {
            'success': False,
            'error': 'Supabase client not installed. Run: pip install supabase',
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
        }


def print_verification_results(results: dict) -> None:
    """Print verification results in a formatted way."""
    print("\n" + "=" * 70)
    print("Supabase Table Verification Results")
    print("=" * 70)

    if 'error' in results:
        print(f"\nError: {results['error']}")
        return

    print(f"\nOverall Status: {'PASS' if results['success'] else 'FAIL'}")
    print("-" * 70)

    print("\nTable Status:")
    for table, info in results.get('tables', {}).items():
        status = "OK" if info.get('exists') and info.get('accessible') else "MISSING"
        icon = "[+]" if status == "OK" else "[-]"
        print(f"  {icon} {table}: {status}")
        if info.get('error'):
            print(f"      Error: {info['error']}")

    if results.get('missing'):
        print(f"\nMissing Tables: {', '.join(results['missing'])}")
        print("\nRun this script without --verify to get the SQL to create missing tables.")

    if results.get('errors'):
        print(f"\nErrors:")
        for error in results['errors']:
            print(f"  - {error}")

    print("\n" + "=" * 70)


# =============================================================================
# Main Functions
# =============================================================================

def get_setup_sql() -> str:
    """Get the complete setup SQL with timestamp."""
    return SCHEMA_SQL.format(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


def get_migration_sql() -> str:
    """Get the migration SQL for updating existing schema."""
    return MIGRATION_SQL


def get_drop_sql() -> str:
    """Get the SQL to drop all tables (use with caution!)."""
    return DROP_TABLES_SQL


def print_sql(sql_type: str = 'setup') -> None:
    """Print the requested SQL to console."""
    if sql_type == 'setup':
        print(get_setup_sql())
    elif sql_type == 'migration':
        print(get_migration_sql())
    elif sql_type == 'drop':
        print("\n" + "!" * 70)
        print("WARNING: This will DELETE ALL DATA!")
        print("!" * 70 + "\n")
        print(get_drop_sql())
    else:
        print(f"Unknown SQL type: {sql_type}")


def save_sql(filepath: str, sql_type: str = 'setup') -> None:
    """Save SQL to a file."""
    if sql_type == 'setup':
        sql = get_setup_sql()
    elif sql_type == 'migration':
        sql = get_migration_sql()
    elif sql_type == 'drop':
        sql = get_drop_sql()
    else:
        print(f"Unknown SQL type: {sql_type}")
        return

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(sql)

    print(f"SQL saved to: {filepath}")


def main():
    """Main entry point for the setup script."""
    parser = argparse.ArgumentParser(
        description='Generate Supabase setup SQL for LocalPulse',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Print setup SQL to console
    python scripts/setup_supabase.py

    # Save setup SQL to file
    python scripts/setup_supabase.py --output setup.sql

    # Print migration SQL (for updating existing tables)
    python scripts/setup_supabase.py --type migration

    # Verify tables exist in Supabase
    python scripts/setup_supabase.py --verify

    # Print drop SQL (use with caution!)
    python scripts/setup_supabase.py --type drop
        """
    )

    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Save SQL to file instead of printing'
    )

    parser.add_argument(
        '--type', '-t',
        type=str,
        choices=['setup', 'migration', 'drop'],
        default='setup',
        help='Type of SQL to generate (default: setup)'
    )

    parser.add_argument(
        '--verify', '-v',
        action='store_true',
        help='Verify that tables exist in Supabase'
    )

    args = parser.parse_args()

    if args.verify:
        # Run verification
        import asyncio
        results = asyncio.run(verify_tables())
        print_verification_results(results)
        sys.exit(0 if results.get('success') else 1)

    if args.output:
        save_sql(args.output, args.type)
    else:
        print_sql(args.type)


if __name__ == '__main__':
    main()
