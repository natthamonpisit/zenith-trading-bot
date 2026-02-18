-- Migration: Add created_at column to positions table
-- Purpose: Supports ordering and timeline views in runtime/dashboard code

ALTER TABLE positions
ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_positions_created_at
ON positions(created_at DESC);
