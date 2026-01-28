-- Migration: Create capital_allocation table
-- Purpose: Virtual wallet separation for capital protection (trading capital vs profit reserve)

CREATE TABLE IF NOT EXISTS capital_allocation (
    id SERIAL PRIMARY KEY,
    mode TEXT NOT NULL CHECK (mode IN ('PAPER', 'LIVE')),

    -- Capital Allocation
    trading_capital NUMERIC NOT NULL DEFAULT 1000.0,
    profit_reserve NUMERIC DEFAULT 0.0,

    -- Auto-Transfer Settings
    auto_transfer_enabled BOOLEAN DEFAULT false,
    transfer_threshold NUMERIC DEFAULT 100.0,
    transfer_percentage NUMERIC DEFAULT 50.0 CHECK (transfer_percentage >= 0 AND transfer_percentage <= 100),

    -- Tracking
    total_deposited NUMERIC DEFAULT 0.0,
    total_withdrawn NUMERIC DEFAULT 0.0,

    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Ensure one record per mode
    UNIQUE(mode)
);

-- Create index
CREATE INDEX IF NOT EXISTS idx_capital_mode ON capital_allocation(mode);

-- Auto-update timestamp trigger
CREATE OR REPLACE FUNCTION update_capital_allocation_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_capital_allocation_timestamp
    BEFORE UPDATE ON capital_allocation
    FOR EACH ROW
    EXECUTE FUNCTION update_capital_allocation_timestamp();

-- Insert default records for both modes
INSERT INTO capital_allocation (mode, trading_capital, profit_reserve, auto_transfer_enabled) VALUES
    ('PAPER', 1000.0, 0.0, false),
    ('LIVE', 1000.0, 0.0, false)
ON CONFLICT (mode) DO NOTHING;
