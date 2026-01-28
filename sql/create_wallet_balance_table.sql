-- Wallet Balance Table
-- Stores Binance wallet balance synced from Railway bot
-- Dashboard reads from this table instead of direct Binance API

CREATE TABLE IF NOT EXISTS wallet_balance (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  
  -- Asset details
  asset TEXT NOT NULL,           -- e.g., "USDT", "BTC"
  free NUMERIC(20, 8) NOT NULL,  -- Available balance
  locked NUMERIC(20, 8) DEFAULT 0, -- Locked in orders
  total NUMERIC(20, 8) NOT NULL, -- Total = free + locked
  
  -- Metadata
  usd_value NUMERIC(15, 2),      -- Estimated USD value (optional)
  is_active BOOLEAN DEFAULT true -- Hide zero balances
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_wallet_updated ON wallet_balance(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_wallet_asset ON wallet_balance(asset);

-- Add comment
COMMENT ON TABLE wallet_balance IS 'Binance wallet balance synced from Railway bot every 5 minutes';
