"""
Clear wallet_balance table to force fresh sync
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db

def clear_wallet_table():
    """Clear wallet_balance table"""
    
    db = get_db()
    
    print("=" * 60)
    print("🗑️ Clearing wallet_balance table...")
    print("=" * 60)
    
    try:
        # Delete all records
        result = db.table("wallet_balance").delete().neq("id", 0).execute()
        
        print(f"\n✅ Table cleared!")
        print(f"💡 Bot will sync fresh data on next cycle (every 5 min)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False

if __name__ == "__main__":
    clear_wallet_table()
