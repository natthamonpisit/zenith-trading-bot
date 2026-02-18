-- Migration: Create rule_evaluations table
-- Purpose: Store hard-rule/checklist verdicts for each candidate decision

CREATE TABLE IF NOT EXISTS rule_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID,
    symbol TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    observed_value TEXT,
    threshold_value TEXT,
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rule_evaluations_run_id ON rule_evaluations(run_id);
CREATE INDEX IF NOT EXISTS idx_rule_evaluations_symbol ON rule_evaluations(symbol);
CREATE INDEX IF NOT EXISTS idx_rule_evaluations_rule_name ON rule_evaluations(rule_name);
CREATE INDEX IF NOT EXISTS idx_rule_evaluations_created_at ON rule_evaluations(created_at DESC);
