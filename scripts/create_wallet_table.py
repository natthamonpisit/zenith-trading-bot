"""
Script to create wallet_balance table in Supabase
Run this once to set up the database schema
"""

from src.database import get_db

def create_wallet_balance_table():
    """Create wallet_balance table in Supabase"""
    
    db = get_db()
    
    sql = """
    -- Wallet Balance Table
    CREATE TABLE IF NOT EXISTS wallet_balance (
      id BIGSERIAL PRIMARY KEY,
      created_at TIMESTAMPTZ DEFAULT NOW(),
      updated_at TIMESTAMPTZ DEFAULT NOW(),
      
      -- Asset details
      asset TEXT NOT NULL,
      free NUMERIC(20, 8) NOT NULL,
      locked NUMERIC(20, 8) DEFAULT 0,
      total NUMERIC(20, 8) NOT NULL,
      
      -- Metadata
      usd_value NUMERIC(15, 2),
      is_active BOOLEAN DEFAULT true
    );

    -- Indexes
    CREATE INDEX IF NOT EXISTS idx_wallet_updated ON wallet_balance(updated_at DESC);
    CREATE INDEX IF NOT EXISTS idx_wallet_asset ON wallet_balance(asset);
    """
    
    try:
        # Note: Supabase Python client doesn't support raw SQL execution
        # We need to use the SQL Editor in Supabase Dashboard
        print("⚠️ Cannot execute raw SQL via Python client")
        print("\n📋 Please run this SQL in Supabase SQL Editor:")
        print("=" * 60)
        print(sql)
        print("=" * 60)
        print("\nSteps:")
        print("1. Go to Supabase Dashboard → SQL Editor")
        print("2. Create new query")
        print("3. Paste the SQL above")
        print("4. Click 'Run'")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    create_wallet_balance_table()
