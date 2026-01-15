-- Migration: Add missing columns to scheduled_jobs table
-- Run this in Supabase SQL Editor
-- Generated: 2026-01-15

-- Add columns if they don't exist
ALTER TABLE scheduled_jobs ADD COLUMN IF NOT EXISTS business_name TEXT;
ALTER TABLE scheduled_jobs ADD COLUMN IF NOT EXISTS location TEXT DEFAULT '';
ALTER TABLE scheduled_jobs ADD COLUMN IF NOT EXISTS owner_email TEXT;

-- Create index
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_business_name ON scheduled_jobs(business_name);

-- Verify the changes
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'scheduled_jobs'
ORDER BY ordinal_position;
