from src.database import get_db
from src.roles.job_spy import Spy
import time

def check_supabase():
    print("\n--- 1. Checking Supabase Tables ---")
    db = get_db()
    required_tables = ['assets', 'market_snapshots', 'ai_analysis', 'trade_signals', 'positions', 'bot_config']
    
    all_good = True
    for table in required_tables:
        try:
            # Try to select 0 rows just to check if table exists
            db.table(table).select("count", count='exact').limit(1).execute()
            print(f"✅ Table '{table}' exists.")
        except Exception as e:
            print(f"❌ Table '{table}' NOT FOUND or Error: {e}")
            all_good = False
    
    return all_good

def check_binance_th():
    print("\n--- 2. Checking Binance TH Connection ---")
    try:
        spy = Spy()
        # Test Fetch
        symbol = "BTC/USDT"
        print(f"Fetching {symbol} from Binance TH...")
        df = spy.fetch_ohlcv(symbol, limit=5)
        
        if df is not None and not df.empty:
            print(f"✅ Connection Success! Fetched {len(df)} candles.")
            print(f"   Last Price: {df['close'].iloc[-1]}")
            return True
        else:
            print("❌ Fetched data is empty.")
            return False
    except Exception as e:
        print(f"❌ Connection Failed: {e}")
        return False

if __name__ == "__main__":
    db_ok = check_supabase()
    api_ok = check_binance_th()
    
    if db_ok and api_ok:
        print("\n🎉 ALL SYSTEMS GO! Ready for Phase 2.")
    else:
        print("\n⚠️ Some checks failed. Please review above.")
