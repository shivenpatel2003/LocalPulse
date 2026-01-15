-- Migration: Add Dynamic Industry Configuration Tables
-- Run this in Supabase SQL Editor
-- Generated: 2026-01-15

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


-- =============================================================================
-- Triggers for updated_at
-- =============================================================================

-- Apply updated_at trigger to new tables (reusing existing function)
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
-- Verification
-- =============================================================================

SELECT
    table_name,
    (SELECT COUNT(*) FROM information_schema.columns c WHERE c.table_name = t.table_name) as column_count
FROM information_schema.tables t
WHERE table_schema = 'public'
    AND table_name IN ('onboarding_sessions', 'industry_configs')
ORDER BY table_name;
