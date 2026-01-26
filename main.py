import time
import schedule
from src.database import get_db
from src.roles.job_spy import Spy
from src.roles.job_ai_analyst import Strategist
from src.roles.job_judge import Judge
from src.roles.job_sniper import Sniper
import pandas as pd

# Initialize Team
db = get_db()
spy = Spy()
strategist = Strategist()
judge = Judge()
sniper = Sniper()

TIMEFRAME = "1h"

def log_activity(role, message, level="INFO"):
    print(f"[{role}] {message}") 
    try:
        db.table("system_logs").insert({
            "role": role,
            "message": message,
            "level": level
        }).execute()
    except Exception as e:
        print(f"Log Error: {e}")

def process_pair(pair):
    """Encapsulated logic for a single trading pair"""
    try:
        # 2. THE SPY: Fetch Data
        print(f"--- 1. Spying on {pair} ---")
        log_activity("Spy", f"🕵️ Scanning {pair} market...")
        df = spy.fetch_ohlcv(pair, TIMEFRAME)
        if df is None: 
            print(f"❌ Data Fetch Failed for {pair}")
            return
            
        df = spy.calculate_indicators(df)
        
        # 3. THE STRATEGIST: AI Analysis
        print("2. Strategist Analyzing...")
        
        # Get asset ID
        asset = db.table("assets").select("id").eq("symbol", pair).execute()
        if not asset.data:
            # Create asset if not exists (Auto-discovery)
            data = db.table("assets").insert({"symbol": pair, "market_type": "spot"}).execute()
            asset_id = data.data[0]['id']
        else:
            asset_id = asset.data[0]['id']

        analysis = strategist.analyze_market(None, pair, df.tail(5).to_dict()) # Send last 5 candles
        if not analysis: 
            print("❌ AI Analysis Failed")
            return
        
        # LOG AI SUMMARY
        log_activity("Strategist", f"[{pair}] Sentiment: {analysis.get('sentiment_score')} | Confidence: {analysis.get('confidence')}%")

        # 4. THE JUDGE: Risk Check
        print("3. Judge Evaluate...")

        # FETCH REAL BALANCE based on Mode
        try:
            mode_cfg = db.table("bot_config").select("value").eq("key", "TRADING_MODE").execute()
            mode = str(mode_cfg.data[0]['value']).replace('"', '').strip() if mode_cfg.data else "PAPER"
        except: mode = "PAPER"

        if mode == "PAPER":
            try:
                sim_wallet = db.table("simulation_portfolio").select("balance").eq("id", 1).execute()
                balance = float(sim_wallet.data[0]['balance']) if sim_wallet.data else 1000.0
            except: balance = 1000.0
        else:
            try:
                # LIVE Mode: Fetch real USDT balance from Binance TH
                bal_data = spy.get_account_balance()
                balance = bal_data['total'].get('USDT', 0.0) if bal_data else 0.0
            except: balance = 0.0
        
        # Convert AI output to needed format
        ai_data = {'confidence': analysis.get('confidence'), 'recommendation': analysis.get('recommendation')}
        tech_data = {'rsi': df['rsi'].iloc[-1]} # Current RSI
        
        verdict = judge.evaluate(ai_data, tech_data, balance)
        print(f"   - Judge Verdict: {verdict.decision} (Bal: ${balance:,.2f})")
        
        # Log Signal to DB
        signal_data = {
            "asset_id": asset_id,
            "signal_type": analysis.get('recommendation'), # BUY/SELL
            "entry_target": verdict.size, # Using size as entry amount for simplicity
            "status": "PENDING" if verdict.decision == "APPROVED" else "REJECTED",
            "judge_reason": verdict.reason,
            "is_sim": (mode == "PAPER")
        }
        signal_entry = db.table("trade_signals").insert(signal_data).execute()
        
        # 5. THE SNIPER: Execution
        if verdict.decision == "APPROVED":
            print("4. Sniper Firing!")
            log_activity("Sniper", f"🔫 Executing {pair}...", "WARNING")
            # Use full signal object
            full_signal = signal_entry.data[0]
            full_signal['assets'] = {'symbol': pair} # Manual hydrate for simplicity
            
            success = sniper.execute_order(full_signal)
            if success:
                 log_activity("Sniper", f"✅ Order Executed for {pair}!", "SUCCESS")
            else:
                 log_activity("Sniper", f"❌ Execution Failed for {pair}", "ERROR")

    except Exception as e:
        print(f"Error processing {pair}: {e}")

def run_bot_cycle():
    print("\n--- 🔄 Multi-Asset Cycle Start ---")
    
    # Reload Judge Config to get latest dashboard settings
    judge.reload_config()
    
    # 1. CHECK KILL SWITCH
    try:
        config = db.table("bot_config").select("*").eq("key", "BOT_STATUS").execute()
        status = str(config.data[0]['value']).replace('"', '').strip() if config.data else "ACTIVE"
        if status == "STOPPED":
             print("⛔ Bot is STOPPED.")
             log_activity("System", "⛔ Bot is STOPPED via Dashboard.", "WARNING")
             return
    except: pass

    # 2. SCAN TOP ASSETS
    top_assets = spy.get_top_symbols(limit=10) # Scan Top 10 Volume Coins
    if not top_assets:
        top_assets = ["BTC/USDT", "ETH/USDT"]

    print(f"🎯 Targeting: {top_assets}")
    
    for pair in top_assets:
        process_pair(pair)
        time.sleep(2) # Be nice to API

def start():
    try:
        log_activity("System", "🚀 Zenith Bot Started (Top 10 Volume Scanner)", "SUCCESS")
        
        # Run once immediately
        run_bot_cycle()
        
        # Schedule: Run every 5 minutes instead of 20s to handle 10 coins gracefully
        schedule.every(5).minutes.do(run_bot_cycle) 
        
        print("Bot scheduled for 5-minute cycles.")
        
        while True:
            try:
                schedule.run_pending()
                time.sleep(1)
            except Exception as e:
                log_activity("System", f"Loop Error: {e}", "ERROR")
                time.sleep(5)
    except Exception as e:
        # Emergency Log
        try:
             db.table("system_logs").insert({"role": "System", "message": f"CRITICAL CRASH: {e}", "level": "ERROR"}).execute()
        except: print(f"Fatal: {e}")

if __name__ == "__main__":
    start()
