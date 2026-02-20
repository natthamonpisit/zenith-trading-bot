-- Migration: Phase 2 order planning + TP ladder state
-- Purpose: Persist deterministic order plans and track TP/breakeven lifecycle on positions.

CREATE TABLE IF NOT EXISTS order_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id TEXT NOT NULL,
    signal_id UUID REFERENCES trade_signals(id) ON DELETE SET NULL,
    position_id UUID REFERENCES positions(id) ON DELETE SET NULL,
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    timeframe TEXT,
    entry_price NUMERIC NOT NULL,
    stop_loss NUMERIC,
    take_profit_1 NUMERIC,
    take_profit_2 NUMERIC,
    risk_per_unit NUMERIC,
    tp1_partial_pct NUMERIC DEFAULT 50 CHECK (tp1_partial_pct BETWEEN 0 AND 100),
    breakeven_price NUMERIC,
    trailing_mode TEXT DEFAULT 'ATR' CHECK (trailing_mode IN ('ATR', 'PERCENT', 'NONE')),
    trailing_value NUMERIC,
    status TEXT DEFAULT 'PLANNED' CHECK (
        status IN ('PLANNED', 'ACTIVE', 'PARTIALLY_FILLED', 'CLOSED', 'CANCELLED', 'FAILED')
    ),
    plan_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_order_plans_run_id ON order_plans(run_id);
CREATE INDEX IF NOT EXISTS idx_order_plans_symbol ON order_plans(symbol);
CREATE INDEX IF NOT EXISTS idx_order_plans_status ON order_plans(status);
CREATE INDEX IF NOT EXISTS idx_order_plans_created_at ON order_plans(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_order_plans_signal_id ON order_plans(signal_id);
CREATE INDEX IF NOT EXISTS idx_order_plans_position_id ON order_plans(position_id);

ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS order_plan_id UUID REFERENCES order_plans(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS initial_stop_loss NUMERIC,
    ADD COLUMN IF NOT EXISTS current_stop_loss NUMERIC,
    ADD COLUMN IF NOT EXISTS take_profit_1 NUMERIC,
    ADD COLUMN IF NOT EXISTS take_profit_2 NUMERIC,
    ADD COLUMN IF NOT EXISTS tp1_partial_pct NUMERIC,
    ADD COLUMN IF NOT EXISTS tp1_hit BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS break_even_armed BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS break_even_price NUMERIC,
    ADD COLUMN IF NOT EXISTS last_tp_event TEXT;

CREATE INDEX IF NOT EXISTS idx_positions_order_plan_id ON positions(order_plan_id);
CREATE INDEX IF NOT EXISTS idx_positions_tp1_hit ON positions(tp1_hit);

ALTER TABLE trade_signals
    ADD COLUMN IF NOT EXISTS order_plan_id UUID;
