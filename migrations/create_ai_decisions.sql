-- Migration: Create ai_decisions table
-- Purpose: Persist every AI tier output for replay/debug

CREATE TABLE IF NOT EXISTS ai_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID,
    symbol TEXT NOT NULL,
    timeframe TEXT,
    tier TEXT NOT NULL CHECK (tier IN ('TIER_1_SUMMARIZER', 'TIER_2_DECISION', 'TIER_3_GOVERNOR')),
    model TEXT,
    prompt_hash TEXT,
    input_hash TEXT,
    output_json JSONB NOT NULL,
    confidence NUMERIC CHECK (confidence BETWEEN 0 AND 100),
    latency_ms INT CHECK (latency_ms >= 0),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_decisions_run_id ON ai_decisions(run_id);
CREATE INDEX IF NOT EXISTS idx_ai_decisions_symbol ON ai_decisions(symbol);
CREATE INDEX IF NOT EXISTS idx_ai_decisions_created_at ON ai_decisions(created_at DESC);
