-- Migration: Add audit logging table
-- Purpose: Track sensitive operations for security review
-- Author: AI Assistant
-- Date: 2026-01-27

-- Create audit_log table
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    
    -- Order execution fields
    symbol TEXT,
    side TEXT,
    amount NUMERIC,
    price NUMERIC,
    is_sim BOOLEAN,
    
    -- Config change fields
    key TEXT,
    old_value TEXT,
    new_value TEXT,
    user TEXT DEFAULT 'system',
    
    -- Balance change fields
    balance_before NUMERIC,
    balance_after NUMERIC,
    reason TEXT,
    
    -- Signal creation fields
    signal_type TEXT,
    status TEXT,
    
    -- Timestamp
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_symbol ON audit_log(symbol) WHERE symbol IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_log(created_at DESC);

-- Add comment
COMMENT ON TABLE audit_log IS 'Security audit trail for sensitive operations';
COMMENT ON COLUMN audit_log.event_type IS 'Type: ORDER_EXECUTED, CONFIG_CHANGED, BALANCE_CHANGED, SIGNAL_CREATED';
COMMENT ON COLUMN audit_log.is_sim IS 'True for simulation/paper trading operations';

-- Verify
SELECT 'Audit log table created successfully' as status;
