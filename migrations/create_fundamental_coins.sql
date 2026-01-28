-- Migration: Create fundamental_coins table
-- Purpose: Store whitelist/blacklist status and fundamental scores for coins

CREATE TABLE IF NOT EXISTS fundamental_coins (
    symbol TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'NEUTRAL' CHECK (status IN ('WHITELIST', 'BLACKLIST', 'NEUTRAL')),
    manual_score INT DEFAULT 5 CHECK (manual_score >= 0 AND manual_score <= 10),
    notes TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for filtering by status
CREATE INDEX IF NOT EXISTS idx_fundamental_status ON fundamental_coins(status);

-- Trigger to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_fundamental_coins_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_fundamental_coins_timestamp
    BEFORE UPDATE ON fundamental_coins
    FOR EACH ROW
    EXECUTE FUNCTION update_fundamental_coins_timestamp();

-- Insert some example data (optional - you can delete this section)
INSERT INTO fundamental_coins (symbol, status, manual_score, notes) VALUES
    ('BTC/USDT', 'WHITELIST', 9, 'Blue chip cryptocurrency'),
    ('ETH/USDT', 'WHITELIST', 9, 'Leading smart contract platform'),
    ('BNB/USDT', 'WHITELIST', 8, 'Exchange token with utility')
ON CONFLICT (symbol) DO NOTHING;
