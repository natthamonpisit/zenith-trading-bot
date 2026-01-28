-- Migration: Create config_change_log table
-- Purpose: Track parameter changes during a trading session

CREATE TABLE IF NOT EXISTS config_change_log (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID REFERENCES trading_sessions(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_config_log_session ON config_change_log(session_id);
CREATE INDEX IF NOT EXISTS idx_config_log_changed ON config_change_log(changed_at DESC);
