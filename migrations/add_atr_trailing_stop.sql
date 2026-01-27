-- Migration: Add ATR support for trailing stops
-- Date: 2026-01-27
-- Description: Add entry_atr column to trade_signals and positions tables

-- Add entry_atr to trade_signals table
ALTER TABLE trade_signals 
ADD COLUMN IF NOT EXISTS entry_atr numeric DEFAULT 0;

COMMENT ON COLUMN trade_signals.entry_atr IS 'ATR (Average True Range) value at signal creation time for dynamic trailing stops';

-- Add entry_atr to positions table  
ALTER TABLE positions 
ADD COLUMN IF NOT EXISTS entry_atr numeric DEFAULT 0;

COMMENT ON COLUMN positions.entry_atr IS 'ATR value at position entry for ATR-based trailing stop calculation';

-- Add new config entries for ATR trailing stop
INSERT INTO bot_config (key, value) 
VALUES 
  ('TRAILING_STOP_USE_ATR', 'false'),
  ('TRAILING_STOP_ATR_MULTIPLIER', '2.0')
ON CONFLICT (key) DO NOTHING;

-- Display config status
SELECT * FROM bot_config 
WHERE key LIKE 'TRAILING%' 
ORDER BY key;
