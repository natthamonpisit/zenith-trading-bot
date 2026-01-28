"""
Fetch recent logs for WalletSync role from Supabase
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db

def check_wallet_logs():
    db = get_db()
    
    print("=" * 60)
    print("🔍 WalletSync Recent Logs (Last 20)")
    print("=" * 60)
    
    try:
        # Fetch logs for WalletSync role
        result = db.table("system_logs")\
            .select("created_at, message, level")\
            .eq("role", "WalletSync")\
            .order("created_at", desc=True)\
            .limit(20)\
            .execute()
        
        if not result.data:
            print("❌ No logs found for WalletSync role")
        
        for log in result.data:
            emoji = "🔴" if log['level'] == "ERROR" else "🟢" if log['level'] == "SUCCESS" else "ℹ️"
            print(f"{log['created_at']} {emoji} [{log['level']}] {log['message']}")
            
    except Exception as e:
        print(f"❌ Error fetching logs: {e}")

if __name__ == "__main__":
    check_wallet_logs()
