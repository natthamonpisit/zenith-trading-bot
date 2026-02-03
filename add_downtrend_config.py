#!/usr/bin/env python3
"""
Add downtrend protection config entries to the bot_config table.
Run this once to initialize the new configuration parameters.
"""
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

def add_downtrend_config():
    """Insert default downtrend protection config values"""
    # Connect to Supabase
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        print("❌ Error: SUPABASE_URL and SUPABASE_KEY must be set in .env")
        return

    db: Client = create_client(url, key)

    # Config entries to add
    configs = [
        {"key": "ENABLE_DOWNTREND_PROTECTION", "value": "false", "description": "Enable market-wide downtrend protection"},
        {"key": "DOWNTREND_PROTECTION_MODE", "value": "MODERATE", "description": "Protection mode: STRICT, MODERATE, or SELECTIVE"},
        {"key": "DOWNTREND_AI_BOOST", "value": "20", "description": "Additional AI confidence % required during downtrends"},
        {"key": "DOWNTREND_SIZE_REDUCTION_PCT", "value": "30", "description": "Position size reduction % in moderate downtrends"},
        {"key": "ADX_TREND_THRESHOLD", "value": "25", "description": "ADX above this value indicates a trending market"}
    ]

    print("Adding downtrend protection config entries...")

    for cfg in configs:
        try:
            # Upsert: insert or update if exists
            result = db.table("bot_config").upsert(cfg).execute()
            print(f"✅ Added/Updated: {cfg['key']} = {cfg['value']}")
        except Exception as e:
            print(f"❌ Error adding {cfg['key']}: {e}")

    print("\n✨ Downtrend protection configuration complete!")
    print("You can now enable it in the dashboard Config page.")

if __name__ == "__main__":
    add_downtrend_config()
