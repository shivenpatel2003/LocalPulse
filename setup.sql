
-- =============================================================================
-- LocalPulse Database Schema for Supabase
-- =============================================================================
-- Generated: 2026-01-15 17:55:11
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
    report_data JSONB DEFAULT '{}',

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
    metadata JSONB DEFAULT '{}',

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
    AND table_name IN ('clients', 'scheduled_jobs', 'reports', 'run_history')
ORDER BY table_name;

-- =============================================================================
-- Setup Complete!
-- =============================================================================
