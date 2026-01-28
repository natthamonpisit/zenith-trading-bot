"""
Manually trigger wallet sync (simulate bot sync)
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db
from src.roles.job_wallet import WalletSync
import ccxt

def trigger_wallet_sync():
    """Manually trigger wallet sync"""
    
    print("=" * 60)
    print("🚀 Triggering Wallet Sync...")
    print("=" * 60)
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Initialize database
    db = get_db()
    print("✅ Database connected")
    
    # Initialize exchange
    try:
        api_key = os.environ.get("BINANCE_API_KEY")
        secret = os.environ.get("BINANCE_SECRET")
        api_url = os.environ.get("BINANCE_API_URL", "https://api.binance.com")
        
        if not api_key or not secret:
            print("❌ Binance credentials not found in .env")
            print("💡 This script needs real API credentials")
            return False
        
        print(f"✅ API Key found")
        print(f"✅ API URL: {api_url}")
        
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret,
            'urls': {'api': {'public': api_url, 'private': api_url}},
            'enableRateLimit': True,
        })
        
        print("✅ Exchange initialized")
        
    except Exception as e:
        print(f"❌ Failed to initialize exchange: {e}")
        return False
    
    # Initialize WalletSync
    try:
        wallet_sync = WalletSync(db, exchange)
        print("✅ WalletSync initialized")
    except Exception as e:
        print(f"❌ Failed to initialize WalletSync: {e}")
        return False
    
    # Run sync
    print("\n🔄 Running wallet sync NOW...")
    print("-" * 60)
    
    try:
        result = wallet_sync.sync_wallet()
        
        if result:
            print("-" * 60)
            print("✅ Wallet sync successful!")
            
            # Check database
            print("\n📊 Verifying database...")
            db_result = db.table("wallet_balance").select("*").execute()
            print(f"✅ Found {len(db_result.data)} assets in database")
            
            if db_result.data:
                print("\n📋 Assets with USD values:")
                for item in db_result.data:
                    usd = item.get('usd_value', 0)
                    print(f"  - {item['asset']}: {item['total']} → ${usd:,.2f} USD")
            
            print("\n" + "=" * 60)
            print("🎉 Sync complete! Check your dashboard now!")
            print("=" * 60)
            return True
        else:
            print("❌ Wallet sync failed")
            return False
            
    except Exception as e:
        print(f"❌ Sync error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = trigger_wallet_sync()
    sys.exit(0 if success else 1)
