-- Migration: Add Exit Reason Tracking to Positions
-- Purpose: Track WHY each position was closed for performance analysis
-- Author: Zenith Trading Bot
-- Date: 2026-01-28

-- Add exit_reason column to positions table
ALTER TABLE positions 
ADD COLUMN IF NOT EXISTS exit_reason TEXT;

-- Create index for fast filtering and analytics
CREATE INDEX IF NOT EXISTS idx_positions_exit_reason 
ON positions(exit_reason);

-- Add comment explaining exit reason categories
COMMENT ON COLUMN positions.exit_reason IS 
'Exit reason categories:
- AI_SELL_SIGNAL: Strategist AI recommended SELL
- TRAILING_STOP: Trailing stop triggered (price dropped from peak)
- STOP_LOSS: Hard stop loss hit
- TAKE_PROFIT: Take profit target reached
- MANUAL_CLOSE: User/dashboard manually closed position
- MAX_HOLD_TIME: Position exceeded max hold duration
- EMERGENCY_CLOSE: Bot emergency stop triggered
- SESSION_END: Position closed when session ended/reset';

-- Backfill existing closed positions with default reason
-- (Only update positions that are closed but have no exit_reason)
UPDATE positions 
SET exit_reason = 'UNKNOWN'
WHERE is_open = FALSE 
AND exit_reason IS NULL;
