"""
Script to RESET all trading data (Hard Reset).
Usage: python3 scripts/reset_data.py

WARNING: This will delete ALL history, positions, and logs.
It will NOT delete your API keys or Bot Config.
"""

import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db

def reset_all_data():
    print("⚠️  WARNING: YOU ARE ABOUT TO DELETE ALL TRADING HISTORY!")
    print("This includes: Positions, Signals, AI Analysis, Sessions, and Logs.")
    print("Your 'bot_config' (API Keys) and 'assets' list will REMAIN intact.")
    
    confirm = input("Are you sure? Type 'RESET' to confirm: ")
    if confirm != 'RESET':
        print("❌ Action cancelled.")
        return

    db = get_db()
    
    tables_to_truncate = [
        "balance_snapshots",
        "config_change_log",
        "positions",
        "orders",
        "trade_signals",
        "ai_analysis",
        "market_snapshots",
        "performance_analytics",
        "system_logs",
        # "assets", # User usually wants to keep the whitelist
        "trading_sessions" # Truncate this LAST due to FK constraints usually, but CASCADE handles it if set, otherwise order matters
    ]

    # Python supabase client's .table().delete() creates a DELETE FROM query.
    # To truncate efficiently, we might need raw SQL or iterate delete.
    # For safety and simple API usage, we will delete all rows where ID is distinct.
    
    print("\n🗑️  Cleaning tables...")

    try:
        # 1. Truncate tables with dependencies in order
        # Delete children first
        
        # Balance & Config Logs (depend on Session)
        print("... Cleaning Balance & Config Logs")
        db.table("balance_snapshots").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        db.table("config_change_log").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()

        # Positions (depends on Assets, Sections)
        print("... Cleaning Positions")
        db.table("positions").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        
        # Orders (depends on Signals)
        print("... Cleaning Orders")
        db.table("orders").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        
        # Signals (depends on AI Analysis)
        print("... Cleaning Signals")
        db.table("trade_signals").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        
        # AI Analysis (depends on Asset, Snapshots)
        print("... Cleaning AI Analysis")
        db.table("ai_analysis").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        
        # Market Snapshots
        print("... Cleaning Market Snapshots")
        db.table("market_snapshots").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        
        # Performance Analytics
        print("... Cleaning Performance Analytics")
        db.table("performance_analytics").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()

        # System Logs
        print("... Cleaning System Logs")
        db.table("system_logs").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        
        # Trading Sessions (Parent of positions/snapshots)
        print("... Cleaning Trading Sessions")
        db.table("trading_sessions").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()

        # Reset Simulation Portfolio
        print("... Resetting Wallet Balance")
        db.table("simulation_portfolio").update({"balance": 1000.0, "total_pnl": 0}).eq("id", 1).execute()

        # Update Last Heartbeat (Reset time to NOW)
        import time
        db.table("bot_config").upsert({"key": "BOT_START_TIME", "value": str(time.time())}).execute()

        # Create initial session so dashboard shows data immediately
        print("... Creating Initial Session (Paper Run #1)")
        from src.session_manager import create_session
        try:
            # Create Paper session
            paper_session_id = create_session(mode='PAPER', start_balance=1000.0, session_name="Paper Run #1")
            if paper_session_id:
                print(f"    ✅ Created PAPER session: Paper Run #1")
            else:
                print("    ⚠️ Failed to create PAPER session")

            # Create Live session
            live_session_id = create_session(mode='LIVE', start_balance=1000.0, session_name="Live Session #1")
            if live_session_id:
                print(f"    ✅ Created LIVE session: Live Session #1")
            else:
                print("    ⚠️ Failed to create LIVE session")
        except Exception as e:
            print(f"    ⚠️ Session creation error (will auto-create on bot restart): {e}")

        print("\n✅ FACTORY RESET COMPLETE!")
        print("You can now restart the bot for a fresh run.")

    except Exception as e:
        print(f"\n❌ Error during reset: {e}")
        print("Tip: If FK violation occurs, try running again or truncate via Supabase SQL Editor.")

if __name__ == "__main__":
    reset_all_data()
