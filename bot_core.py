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

def run_bot_cycle():
    print(f"\n--- 🔄 Bot Cycle Start: {pd.Timestamp.now()} ---")
    
    # 1. CHECK KILL SWITCH
    # config = db.table("bot_config").select("*").eq("key", "BOT_STATUS").execute()
    # if config.data and config.data[0]['value'] == "STOPPED":
    #     print("⛔ Bot is STOPPED via Dashboard.")
    #     return

    # 2. THE SPY: Fetch Data
    print("🕵️ Spy: Looking at charts...")
    df = spy.fetch_ohlcv(TRADING_PAIR, TIMEFRAME)
    if df is None: return
    df = spy.calculate_indicators(df)
    
    # Save Snapshot to DB (Optional, for history)
    # db.table("market_snapshots").insert({...})

    # 3. THE STRATEGIST: AI Analysis
    print("🧠 Strategist: Analyzing...")
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
    
    print(f"   Sentiment: {analysis.get('sentiment_score')} | Conf: {analysis.get('confidence')}%")

    # 4. THE JUDGE: Risk Check
    print("⚖️ Judge: Reviewing...")
    # Convert AI output to needed format
    ai_data = {'confidence': analysis.get('confidence'), 'recommendation': analysis.get('recommendation')}
    tech_data = {'rsi': df['rsi'].iloc[-1]} # Current RSI
    balance = 1000 # Mock balance for now, or fetch from spy.exchange.fetch_balance()
    
    verdict = judge.evaluate(ai_data, tech_data, balance)
    print(f"   Verdict: {verdict.decision} ({verdict.reason})")
    
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
        print("🔫 Sniper: Taking the shot!")
        # Use full signal object
        full_signal = signal_entry.data[0]
        full_signal['assets'] = {'symbol': TRADING_PAIR} # Manual hydrate for simplicity
        
        sniper.execute_order(full_signal)

def start():
    print("🚀 Zenith Bot Started (Binance TH Edition)")
    print(f"Target: {TRADING_PAIR}")
    
    # Run once immediately
    run_bot_cycle()
    
    # Schedule
    schedule.every(10).seconds.do(run_bot_cycle) # Fast loop for demo
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    start()
