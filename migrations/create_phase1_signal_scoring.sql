-- Migration: Phase 1 signal scoring and snapshot storage
-- Purpose: Persist candidate universe snapshots, indicator feature snapshots, and score breakdowns.

CREATE TABLE IF NOT EXISTS universe_snapshot (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    asset_class TEXT NOT NULL DEFAULT 'crypto',
    rank INT NOT NULL DEFAULT 0,
    source TEXT,
    volume NUMERIC,
    status TEXT,
    whitelist_pass BOOLEAN,
    inclusion_reason TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_universe_snapshot_snapshot_id ON universe_snapshot(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_universe_snapshot_symbol ON universe_snapshot(symbol);
CREATE INDEX IF NOT EXISTS idx_universe_snapshot_asset_class ON universe_snapshot(asset_class);
CREATE INDEX IF NOT EXISTS idx_universe_snapshot_created_at ON universe_snapshot(created_at DESC);

CREATE TABLE IF NOT EXISTS feature_snapshot (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    close NUMERIC,
    volume NUMERIC,
    quote_volume NUMERIC,
    rsi NUMERIC,
    macd NUMERIC,
    macd_signal NUMERIC,
    ema_20 NUMERIC,
    ema_50 NUMERIC,
    ema_200 NUMERIC,
    atr NUMERIC,
    adx NUMERIC,
    price_position_score NUMERIC,
    ai_confidence NUMERIC,
    sentiment_score NUMERIC,
    features_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feature_snapshot_run_id ON feature_snapshot(run_id);
CREATE INDEX IF NOT EXISTS idx_feature_snapshot_symbol_tf ON feature_snapshot(symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_feature_snapshot_created_at ON feature_snapshot(created_at DESC);

CREATE TABLE IF NOT EXISTS signal_score (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    total_score NUMERIC NOT NULL,
    threshold NUMERIC NOT NULL DEFAULT 60,
    passed_threshold BOOLEAN NOT NULL DEFAULT FALSE,
    component_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
    weighted_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
    weights JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signal_score_run_id ON signal_score(run_id);
CREATE INDEX IF NOT EXISTS idx_signal_score_symbol_tf ON signal_score(symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_signal_score_passed ON signal_score(passed_threshold);
CREATE INDEX IF NOT EXISTS idx_signal_score_created_at ON signal_score(created_at DESC);
