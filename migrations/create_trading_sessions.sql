-- Migration: Create trading_sessions table
-- Purpose: Track each trading session (paper or live) with comprehensive performance metrics

CREATE TABLE IF NOT EXISTS trading_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_name TEXT,
    mode TEXT NOT NULL CHECK (mode IN ('PAPER', 'LIVE')),
    start_balance NUMERIC NOT NULL,
    current_balance NUMERIC NOT NULL,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,

    -- Aggregate Performance Metrics (updated after each trade close)
    total_trades INT DEFAULT 0,
    winning_trades INT DEFAULT 0,
    losing_trades INT DEFAULT 0,
    gross_profit NUMERIC DEFAULT 0,
    gross_loss NUMERIC DEFAULT 0,
    net_pnl NUMERIC DEFAULT 0,

    -- Advanced Trading Metrics
    largest_win NUMERIC DEFAULT 0,
    largest_loss NUMERIC DEFAULT 0,
    avg_win NUMERIC DEFAULT 0,
    avg_loss NUMERIC DEFAULT 0,
    win_rate NUMERIC DEFAULT 0,
    profit_factor NUMERIC DEFAULT 0,
    max_drawdown NUMERIC DEFAULT 0,
    max_drawdown_pct NUMERIC DEFAULT 0,

    -- Config Snapshot (bot_config at session start)
    config_snapshot JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_sessions_mode ON trading_sessions(mode);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON trading_sessions(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_sessions_started ON trading_sessions(started_at DESC);

-- Ensure only one active session per mode
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_per_mode ON trading_sessions(mode) WHERE is_active = true;
