-- Migration: Create chart_candle_cache table
-- Purpose: Cache candles for fast dashboard rendering

CREATE TABLE IF NOT EXISTS chart_candle_cache (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    ts_open TIMESTAMPTZ NOT NULL,
    open NUMERIC NOT NULL,
    high NUMERIC NOT NULL,
    low NUMERIC NOT NULL,
    close NUMERIC NOT NULL,
    volume NUMERIC NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'exchange',
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (symbol, timeframe, ts_open)
);

CREATE INDEX IF NOT EXISTS idx_chart_cache_updated_at ON chart_candle_cache(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chart_cache_symbol_tf ON chart_candle_cache(symbol, timeframe);
