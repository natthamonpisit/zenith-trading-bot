-- Migration: Add session_id column to positions table
-- Purpose: Link each position to its trading session

ALTER TABLE positions
ADD COLUMN IF NOT EXISTS session_id UUID REFERENCES trading_sessions(id);

-- Index for joins
CREATE INDEX IF NOT EXISTS idx_positions_session ON positions(session_id);
