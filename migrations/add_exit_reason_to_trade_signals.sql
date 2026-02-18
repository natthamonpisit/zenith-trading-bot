-- Migration: Add exit_reason column to trade_signals table
-- Purpose: Preserve SELL context/reason generated before execution

ALTER TABLE trade_signals
ADD COLUMN IF NOT EXISTS exit_reason TEXT;

COMMENT ON COLUMN trade_signals.exit_reason IS
'Reason for SELL signal/context (e.g., AI_SELL_SIGNAL details)';
