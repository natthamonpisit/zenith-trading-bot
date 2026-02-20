"""
RUN THIS SQL IN SUPABASE SQL EDITOR
"""

SQL_SCHEMA = """
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Assets Table (Target list)
CREATE TABLE IF NOT EXISTS assets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol TEXT NOT NULL UNIQUE,
    market_type TEXT CHECK (market_type IN ('spot', 'futures')),
    status TEXT DEFAULT 'active', -- active, blacklisted
    fundamentals JSONB, -- ROE, PEG, Revenue
    tags TEXT[],
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Market Snapshots (Technical Data)
CREATE TABLE IF NOT EXISTS market_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_id UUID REFERENCES assets(id),
    timeframe TEXT DEFAULT '1h',
    close_price NUMERIC,
    rsi NUMERIC,
    macd NUMERIC,
    atr NUMERIC,
    extra_indicators JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. AI Analysis (The Brain)
CREATE TABLE IF NOT EXISTS ai_analysis (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_id UUID REFERENCES assets(id),
    snapshot_id UUID REFERENCES market_snapshots(id),
    sentiment_score NUMERIC CHECK (sentiment_score BETWEEN -1 AND 1),
    ai_confidence NUMERIC CHECK (ai_confidence BETWEEN 0 AND 100),
    reasoning TEXT,
    news_ref JSONB,
    model_version TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Trade Signals (The Verdict)
CREATE TABLE IF NOT EXISTS trade_signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_id UUID REFERENCES assets(id),
    ai_analysis_id UUID REFERENCES ai_analysis(id),
    signal_type TEXT CHECK (signal_type IN ('BUY', 'SELL', 'HOLD', 'REJECT')),
    entry_target NUMERIC,
    stop_loss NUMERIC,
    take_profit NUMERIC,
    leverage INTEGER DEFAULT 1,
    status TEXT DEFAULT 'pending', -- pending, executed, cancelled, expired
    judge_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. Orders (Execution)
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    signal_id UUID REFERENCES trade_signals(id),
    exchange_order_id TEXT,
    price_filled NUMERIC,
    quantity NUMERIC,
    fee NUMERIC,
    status TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. Positions (Holding)
CREATE TABLE IF NOT EXISTS positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_id UUID REFERENCES assets(id),
    side TEXT CHECK (side IN ('LONG', 'SHORT')),
    entry_avg NUMERIC,
    quantity NUMERIC,
    leverage INTEGER,
    unrealized_pnl NUMERIC,
    is_open BOOLEAN DEFAULT TRUE,
    opened_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    closed_at TIMESTAMP WITH TIME ZONE
);

-- Trailing Stop columns for positions
ALTER TABLE positions ADD COLUMN IF NOT EXISTS highest_price_seen NUMERIC;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS trailing_stop_price NUMERIC;

-- Phase 2 columns for risk/TP lifecycle
ALTER TABLE positions ADD COLUMN IF NOT EXISTS order_plan_id UUID;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS initial_stop_loss NUMERIC;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS current_stop_loss NUMERIC;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS take_profit_1 NUMERIC;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS take_profit_2 NUMERIC;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS tp1_partial_pct NUMERIC;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS tp1_hit BOOLEAN DEFAULT FALSE;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS break_even_armed BOOLEAN DEFAULT FALSE;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS break_even_price NUMERIC;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS last_tp_event TEXT;

-- Phase 2: Order Plans
CREATE TABLE IF NOT EXISTS order_plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id TEXT NOT NULL,
    signal_id UUID REFERENCES trade_signals(id) ON DELETE SET NULL,
    position_id UUID REFERENCES positions(id) ON DELETE SET NULL,
    asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
    symbol TEXT NOT NULL,
    side TEXT CHECK (side IN ('BUY', 'SELL')),
    timeframe TEXT,
    entry_price NUMERIC,
    stop_loss NUMERIC,
    take_profit_1 NUMERIC,
    take_profit_2 NUMERIC,
    risk_per_unit NUMERIC,
    tp1_partial_pct NUMERIC,
    breakeven_price NUMERIC,
    trailing_mode TEXT,
    trailing_value NUMERIC,
    status TEXT DEFAULT 'PLANNED',
    plan_payload JSONB DEFAULT '{}'::jsonb,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_order_plans_symbol ON order_plans(symbol);
CREATE INDEX IF NOT EXISTS idx_order_plans_status ON order_plans(status);
CREATE INDEX IF NOT EXISTS idx_order_plans_created_at ON order_plans(created_at DESC);

-- Link signals to order plan (optional)
ALTER TABLE trade_signals ADD COLUMN IF NOT EXISTS order_plan_id UUID;

-- 7. Bot Config (Dynamic Settings)
CREATE TABLE IF NOT EXISTS bot_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Seed initial config (keys match Judge + Config Page conventions)
INSERT INTO bot_config (key, value, description)
VALUES
('MAX_RISK_PER_TRADE', '"2.0"', 'Percentage of portfolio risk per trade'),
('RSI_THRESHOLD', '"75"', 'RSI threshold - reject BUY if RSI above this'),
('AI_CONF_THRESHOLD', '"60"', 'Minimum AI confidence to consider a trade'),
('POSITION_SIZE_PCT', '"5.0"', 'Position size as percentage of wallet'),
('MAX_OPEN_POSITIONS', '"5"', 'Maximum number of concurrent open positions'),
('TRADING_MODE', '"PAPER"', 'PAPER or LIVE trading mode'),
('TIMEFRAME', '"1h"', 'Default trading timeframe'),
('MIN_VOLUME', '"10000"', 'Minimum 24h volume in USDT'),
('TRADING_UNIVERSE', '"TOP_100"', 'ALL, SAFE_LIST, TOP_30, or TOP_100'),
('WHITELIST_POLICY', '"RELAXED"', 'STRICT, RELAXED, or IGNORE'),
('RADAR_SCAN_LIMIT', '"100"', 'Maximum symbols requested from Radar scan'),
('FARMING_INTERVAL_HOURS', '"12"', 'Hours between farming cycles'),
('MIN_TOTAL_SCORE_TO_CANDIDATE', '"60"', 'Minimum score (0-100) required to pass candidate score threshold'),
('ENABLE_SIGNAL_SCORE_GATE', '"false"', 'When true, BUY signals below minimum score are rejected'),
('SCORE_LIQUIDITY_MIN_VOLUME', '"10000"', 'Reference quote volume baseline used by signal score liquidity component'),
('SCORE_WEIGHT_TREND', '"25"', 'Signal score weight: trend component'),
('SCORE_WEIGHT_MOMENTUM', '"20"', 'Signal score weight: momentum component'),
('SCORE_WEIGHT_VOLATILITY', '"15"', 'Signal score weight: volatility component'),
('SCORE_WEIGHT_LIQUIDITY', '"20"', 'Signal score weight: liquidity component'),
('SCORE_WEIGHT_STRUCTURE', '"10"', 'Signal score weight: structure component'),
('SCORE_WEIGHT_PORTFOLIO', '"10"', 'Signal score weight: portfolio-fit component'),
('TRAILING_STOP_ENABLED', '"true"', 'Enable trailing stop loss'),
('TRAILING_STOP_PCT', '"3.0"', 'Trailing stop percentage below peak price'),
('MIN_PROFIT_TO_TRAIL_PCT', '"1.0"', 'Minimum profit % before trailing stop activates'),
('ORDER_PLAN_ENABLED', '"true"', 'Enable deterministic order planning before execution'),
('STOP_LOSS_ATR_MULTIPLIER', '"1.8"', 'Initial stop distance = ATR * multiplier'),
('MIN_STOP_LOSS_PCT', '"0.8"', 'Minimum stop-loss distance as % of entry'),
('ENABLE_TP_LADDER', '"true"', 'Enable TP ladder monitor (TP1 partial, TP2 full)'),
('TP1_R_MULTIPLE', '"1.0"', 'TP1 distance in R multiple'),
('TP2_R_MULTIPLE', '"2.0"', 'TP2 distance in R multiple'),
('TP1_PARTIAL_PCT', '"50"', 'Partial close percent at TP1'),
('BREAKEVEN_BUFFER_PCT', '"0.1"', 'Promote stop to entry + buffer percent after TP1'),
('ORDER_PLAN_TRAILING_MODE', '"ATR"', 'Preferred trailing mode after plan activation: ATR|PERCENT|NONE'),
('ENABLE_DOWNTREND_PROTECTION', '"false"', 'Enable market-wide downtrend protection'),
('DOWNTREND_PROTECTION_MODE', '"MODERATE"', 'Protection mode: STRICT, MODERATE, or SELECTIVE'),
('DOWNTREND_AI_BOOST', '"20"', 'Additional AI confidence % required during downtrends'),
('DOWNTREND_SIZE_REDUCTION_PCT', '"30"', 'Position size reduction % in moderate downtrends'),
('ADX_TREND_THRESHOLD', '"25"', 'ADX above this value indicates a trending market')
ON CONFLICT DO NOTHING;

-- 8. System Logs
CREATE TABLE IF NOT EXISTS system_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    level TEXT, -- INFO, ERROR, WARNING
    role TEXT, -- HeadHunter, Sniper, etc.
    message TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 9. Performance Analytics (Post-Mortem)
CREATE TABLE IF NOT EXISTS performance_analytics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trade_signal_id UUID REFERENCES trade_signals(id),
    outcome TEXT CHECK (outcome IN ('WIN', 'LOSS', 'BREAK_EVEN')),
    pnl_percent NUMERIC,
    exit_reason TEXT,
    -- Context Snapshot
    entry_ai_confidence NUMERIC,
    entry_ai_sentiment NUMERIC,
    entry_ai_reason TEXT,
    entry_rsi NUMERIC,
    market_trend TEXT,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
"""

def print_instructions():
    print("----- ZENITH DATABASE SETUP -----")
    print("Please copy the SQL content from this file and run it inside the Supabase SQL Editor.")
    print("This ensures all tables, constraints, and relationships are created correctly.")

if __name__ == "__main__":
    print_instructions()
