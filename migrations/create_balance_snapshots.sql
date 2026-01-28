-- Migration: Create balance_snapshots table
-- Purpose: Periodic balance snapshots for drawdown calculation

CREATE TABLE IF NOT EXISTS balance_snapshots (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID REFERENCES trading_sessions(id) ON DELETE CASCADE,
    balance NUMERIC NOT NULL,
    equity NUMERIC NOT NULL,
    peak_equity NUMERIC NOT NULL,
    drawdown NUMERIC DEFAULT 0,
    drawdown_pct NUMERIC DEFAULT 0,
    snapshot_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_snapshots_session ON balance_snapshots(session_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_time ON balance_snapshots(snapshot_at DESC);
