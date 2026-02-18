-- Migration: Create farming_history table
-- Purpose: Track each farming cycle for dashboard/debug visibility

CREATE TABLE IF NOT EXISTS farming_history (
    id BIGSERIAL PRIMARY KEY,
    start_time TIMESTAMPTZ DEFAULT NOW(),
    end_time TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'IN_PROGRESS',
    candidates_found INT DEFAULT 0,
    logs TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_farming_history_start_time
ON farming_history(start_time DESC);
