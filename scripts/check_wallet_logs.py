"""
Check system logs for wallet sync errors
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db

def check_wallet_logs():
    """Check system logs for wallet sync messages"""
    
    db = get_db()
    
    print("=" * 60)
    print("🔍 Checking WalletSync logs...")
    print("=" * 60)
    
    try:
        # Get recent wallet sync logs
        result = db.table("system_logs")\
            .select("*")\
            .eq("role", "WalletSync")\
            .order("created_at", desc=True)\
            .limit(10)\
            .execute()
        
        if result.data:
            print(f"\n📋 Found {len(result.data)} WalletSync logs:\n")
            for log in result.data:
                level = log.get('level', 'INFO')
                msg = log.get('message', '')
                created = log.get('created_at', '')
                
                emoji = "✅" if level == "SUCCESS" else "⚠️" if level == "WARNING" else "❌" if level == "ERROR" else "ℹ️"
                print(f"{emoji} [{level}] {msg}")
                print(f"   Time: {created}\n")
        else:
            print("\n❌ No WalletSync logs found")
            print("💡 This means wallet sync hasn't run yet or failed silently")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    check_wallet_logs()
