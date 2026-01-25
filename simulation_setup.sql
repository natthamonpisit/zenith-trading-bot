-- Add simulation flag to existing tables
ALTER TABLE trade_signals ADD COLUMN IF NOT EXISTS is_sim BOOLEAN DEFAULT FALSE;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS is_sim BOOLEAN DEFAULT FALSE;

-- Create Simulation Portfolio table
CREATE TABLE IF NOT EXISTS simulation_portfolio (
    id SERIAL PRIMARY KEY,
    balance NUMERIC DEFAULT 1000.0,
    total_pnl NUMERIC DEFAULT 0.0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Insert default simulation wallet if not exists
INSERT INTO simulation_portfolio (id, balance) 
SELECT 1, 1000.0 
WHERE NOT EXISTS (SELECT 1 FROM simulation_portfolio WHERE id = 1);

-- Add Configuration Key for Mode
INSERT INTO bot_config (key, value) 
VALUES ('TRADING_MODE', 'PAPER') 
ON CONFLICT (key) DO NOTHING;
