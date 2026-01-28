"""
Check AI_MODEL in database
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db

def check_ai_model():
    """Check AI_MODEL in bot_config"""
    
    db = get_db()
    
    print("=" * 60)
    print("🔍 Checking AI_MODEL in database...")
    print("=" * 60)
    
    try:
        # Check AI_MODEL
        result = db.table("bot_config").select("*").eq("key", "AI_MODEL").execute()
        
        if result.data:
            print(f"\n✅ AI_MODEL found!")
            print(f"Value: {result.data[0]['value']}")
            print(f"Updated: {result.data[0].get('updated_at', 'N/A')}")
        else:
            print("\n❌ AI_MODEL not found in database")
            print("💡 Strategist hasn't initialized yet or failed to save")
        
        # Check all bot_config keys
        print("\n" + "=" * 60)
        print("📋 All bot_config keys:")
        print("=" * 60)
        
        all_config = db.table("bot_config").select("key, value").execute()
        for item in all_config.data:
            print(f"  - {item['key']}: {item['value']}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False

if __name__ == "__main__":
    check_ai_model()
