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

-- 7. Bot Config (Dynamic Settings)
CREATE TABLE IF NOT EXISTS bot_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Seed initial config
INSERT INTO bot_config (key, value, description) 
VALUES 
('MAX_RISK_PER_TRADE', '2.0', 'Percentage of portfolio risk per trade'),
('RSI_OVERBOUGHT', '70', 'RSI threshold for overbought'),
('RSI_OVERSOLD', '30', 'RSI threshold for oversold'),
('AI_MIN_CONFIDENCE', '75', 'Minimum AI confidence to consider a trade')
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
