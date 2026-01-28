-- Migration: Add exit_price and pnl columns to positions table
-- Required by Fix #7: P&L tracking on position close
-- Run this in Supabase SQL Editor

ALTER TABLE positions
ADD COLUMN IF NOT EXISTS exit_price FLOAT DEFAULT NULL,
ADD COLUMN IF NOT EXISTS pnl FLOAT DEFAULT NULL;

-- Optional: Add comment for documentation
COMMENT ON COLUMN positions.exit_price IS 'Price at which the position was closed';
COMMENT ON COLUMN positions.pnl IS 'Profit/Loss in USDT (exit_price - entry_avg) * quantity';
