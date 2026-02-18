-- Migration: Create post_trade_attribution table
-- Purpose: Capture why a trade won/lost for tuning and replay analytics

CREATE TABLE IF NOT EXISTS post_trade_attribution (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    position_id UUID REFERENCES positions(id) ON DELETE SET NULL,
    run_id UUID,
    outcome TEXT NOT NULL CHECK (outcome IN ('WIN', 'LOSS', 'BREAK_EVEN')),
    pnl NUMERIC NOT NULL DEFAULT 0,
    mfe NUMERIC,
    mae NUMERIC,
    exit_reason TEXT,
    violated_rule TEXT,
    ai_vs_rule_alignment TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_post_trade_attr_position ON post_trade_attribution(position_id);
CREATE INDEX IF NOT EXISTS idx_post_trade_attr_run_id ON post_trade_attribution(run_id);
CREATE INDEX IF NOT EXISTS idx_post_trade_attr_outcome ON post_trade_attribution(outcome);
CREATE INDEX IF NOT EXISTS idx_post_trade_attr_created_at ON post_trade_attribution(created_at DESC);
