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

TRADING_PAIR = "BTC/USDT" 
TIMEFRAME = "1h"
# Helper: Log activity to DB so Dashboard can see it live
def log_activity(role, message, level="INFO"):
    print(f"{role}: {message}")
    try:
        db.table("system_logs").insert({
            "role": role,
            "message": message,
            "level": level
        }).execute()
    except Exception as e:
        print(f"Log Error: {e}")

def run_bot_cycle():
    # log_activity("System", f"--- 🔄 Bot Cycle Start: {pd.Timestamp.now()} ---")
    
    # 1. CHECK KILL SWITCH
    try:
        config = db.table("bot_config").select("*").eq("key", "BOT_STATUS").execute()
        if config.data and config.data[0]['value'] == "STOPPED":
             log_activity("System", "⛔ Bot is STOPPED via Dashboard.", "WARNING")
             return
    except: pass

    # 2. THE SPY: Fetch Data
    log_activity("Spy", "🕵️ Scanning BTC/USDT market...")
    df = spy.fetch_ohlcv(TRADING_PAIR, TIMEFRAME)
    if df is None: 
        log_activity("Spy", "❌ Failed to fetch market data", "ERROR")
        return
    df = spy.calculate_indicators(df)
    
    # 3. THE STRATEGIST: AI Analysis
    log_activity("Strategist", "🧠 Analyzing market trends...")
    # Get asset ID
    asset = db.table("assets").select("id").eq("symbol", TRADING_PAIR).execute()
    if not asset.data:
        # Create asset if not exists (Auto-discovery)
        data = db.table("assets").insert({"symbol": TRADING_PAIR, "market_type": "spot"}).execute()
        asset_id = data.data[0]['id']
    else:
        asset_id = asset.data[0]['id']

    analysis = strategist.analyze_market(None, TRADING_PAIR, df.tail(5).to_dict()) # Send last 5 candles
    if not analysis: return
    
    log_activity("Strategist", f"Analyzed Sentiment: {analysis.get('sentiment_score')} | Confidence: {analysis.get('confidence')}%")

    # 4. THE JUDGE: Risk Check
    log_activity("Judge", "⚖️ Evaluating Risk Protocols...")
    
    # Convert AI output to needed format
    ai_data = {'confidence': analysis.get('confidence'), 'recommendation': analysis.get('recommendation')}
    tech_data = {'rsi': df['rsi'].iloc[-1]} # Current RSI
    balance = 1000 # Mock balance for now, or fetch from spy.exchange.fetch_balance()
    
    verdict = judge.evaluate(ai_data, tech_data, balance)
    log_activity("Judge", f"Verdict: {verdict.decision} ({verdict.reason})")
    
    # Log Signal to DB
    signal_data = {
        "asset_id": asset_id,
        "signal_type": analysis.get('recommendation'), # BUY/SELL
        "entry_target": verdict.size, # Using size as entry amount for simplicity
        "status": "PENDING" if verdict.decision == "APPROVED" else "REJECTED",
        "judge_reason": verdict.reason
    }
    signal_entry = db.table("trade_signals").insert(signal_data).execute()
    
    # 5. THE SNIPER: Execution
    if verdict.decision == "APPROVED":
        log_activity("Sniper", "🔫 Loading execution module...")
        # Use full signal object
        full_signal = signal_entry.data[0]
        full_signal['assets'] = {'symbol': TRADING_PAIR} # Manual hydrate for simplicity
        
        success = sniper.execute_order(full_signal)
        if success:
             log_activity("Sniper", "✅ Order Executed Successfully!", "SUCCESS")
        else:
             log_activity("Sniper", "❌ Order Execution Failed", "ERROR")

def start():
    try:
        log_activity("System", "🚀 Zenith Bot Started (Binance TH Edition)", "SUCCESS")
        print(f"Target: {TRADING_PAIR}")
        
        # Run once immediately
        run_bot_cycle()
        
        # Schedule
        schedule.every(20).seconds.do(run_bot_cycle) # Slower loop to avoid spam
        
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
