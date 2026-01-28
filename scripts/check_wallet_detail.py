"""
Check wallet_balance table with detailed field values
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db
import json

def check_wallet_detail():
    """Check wallet_balance table with all fields"""
    
    db = get_db()
    
    print("=" * 60)
    print("🔍 Checking wallet_balance table (detailed)...")
    print("=" * 60)
    
    try:
        # Try to query the table
        result = db.table("wallet_balance").select("*").execute()
        
        print(f"\n✅ Table exists!")
        print(f"📊 Rows found: {len(result.data)}")
        
        if result.data:
            print("\n📋 Detailed data:")
            for item in result.data:
                print("\n" + "-" * 60)
                print(json.dumps(item, indent=2, default=str))
        else:
            print("\n⚠️ Table is empty - waiting for bot to sync")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False

if __name__ == "__main__":
    check_wallet_detail()
