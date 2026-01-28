"""
Check wallet_balance table in Supabase
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db

def check_wallet_table():
    """Check if wallet_balance table exists and has data"""
    
    db = get_db()
    
    print("=" * 60)
    print("🔍 Checking wallet_balance table...")
    print("=" * 60)
    
    try:
        # Try to query the table
        result = db.table("wallet_balance").select("*").execute()
        
        print(f"\n✅ Table exists!")
        print(f"📊 Rows found: {len(result.data)}")
        
        if result.data:
            print("\n📋 Sample data:")
            for item in result.data[:5]:  # Show first 5 rows
                print(f"  - {item.get('asset')}: {item.get('total')} (Free: {item.get('free')}, Locked: {item.get('locked')})")
                print(f"    Updated: {item.get('updated_at')}")
        else:
            print("\n⚠️ Table is empty - waiting for bot to sync")
            print("💡 Bot syncs wallet every 5 minutes")
            print("💡 Check Railway logs to see if bot is running")
        
        return True
        
    except Exception as e:
        error_str = str(e).lower()
        
        if "relation" in error_str and "does not exist" in error_str:
            print("\n❌ Table does NOT exist!")
            print("💡 Run the SQL script in Supabase SQL Editor")
        else:
            print(f"\n❌ Error: {e}")
        
        return False

if __name__ == "__main__":
    check_wallet_table()
