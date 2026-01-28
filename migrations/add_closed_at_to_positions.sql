-- Migration: Add closed_at column to positions table
-- Purpose: Track when positions are closed for proper historical ordering

ALTER TABLE positions
ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;

-- Create index for ordering by closed_at
CREATE INDEX IF NOT EXISTS idx_positions_closed_at ON positions(closed_at DESC);

-- Backfill closed_at for existing closed positions (set to created_at or now)
UPDATE positions
SET closed_at = COALESCE(created_at, NOW())
WHERE is_open = false AND closed_at IS NULL;
