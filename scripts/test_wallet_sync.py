"""
Test wallet sync locally
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db
from src.roles.job_wallet import WalletSync
import ccxt

def test_wallet_sync():
    """Test wallet sync functionality"""
    
    print("=" * 60)
    print("🧪 Testing Wallet Sync...")
    print("=" * 60)
    
    # Initialize database
    db = get_db()
    
    # Initialize exchange
    try:
        from dotenv import load_dotenv
        load_dotenv()
        
        api_key = os.environ.get("BINANCE_API_KEY")
        secret = os.environ.get("BINANCE_SECRET")
        api_url = os.environ.get("BINANCE_API_URL", "https://api.binance.com")
        
        if not api_key or not secret:
            print("❌ Binance credentials not found in .env")
            return False
        
        print(f"✅ API Key found: {api_key[:8]}...")
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
    print("\n🔄 Running wallet sync...")
    try:
        result = wallet_sync.sync_wallet()
        
        if result:
            print("✅ Wallet sync successful!")
            
            # Check database
            print("\n📊 Checking database...")
            db_result = db.table("wallet_balance").select("*").execute()
            print(f"✅ Found {len(db_result.data)} assets in database")
            
            if db_result.data:
                print("\n📋 Assets:")
                for item in db_result.data:
                    print(f"  - {item['asset']}: {item['total']}")
            
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
    success = test_wallet_sync()
    print("\n" + "=" * 60)
    if success:
        print("✅ Test PASSED - Wallet sync is working!")
    else:
        print("❌ Test FAILED - Check errors above")
    print("=" * 60)
