import time
import schedule
import threading
import os
from src.database import get_db

# --- IMPORT NEW ROLES ---
from src.roles.job_screener import HeadHunter
from src.roles.job_price import PriceSpy
from src.roles.job_news import NewsSpy
from src.roles.job_scout import Radar
from src.roles.job_analysis import Strategist, Judge
from src.roles.job_executor import SniperExecutor

# Initialize Team
db = get_db()
head_hunter = HeadHunter(db) # Pass DB for Config/Fundamental Data
price_spy = PriceSpy()
news_spy = NewsSpy()
radar = Radar(price_spy) # Radar uses PriceSpy
strategist = Strategist()
judge = Judge()
sniper = SniperExecutor()

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

def process_pair(pair, timeframe):
    """Encapsulated logic for a single trading pair"""
    try:
        # 1. SPY A (Price)
        print(f"--- 1. SPY A: Fetching Price for {pair} ({timeframe}) ---")
        log_activity("Spy", f"🕵️ Scanning {pair} ({timeframe}) market...")
        df = price_spy.fetch_ohlcv(pair, timeframe)
        if df is None: 
            print(f"❌ Data Fetch Failed for {pair}")
            return
            
        df = price_spy.calculate_indicators(df)
        
        # 2. STRATEGIST (AI)
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

        # 3. JUDGE (Rules)
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
                # LIVE Mode: Fetch real USDT balance
                bal_data = price_spy.get_account_balance()
                balance = bal_data['total'].get('USDT', 0.0) if bal_data else 0.0
            except: balance = 0.0
        
        # Convert AI output to needed format
        ai_data = {'confidence': analysis.get('confidence'), 'recommendation': analysis.get('recommendation')}
        tech_data = {
            'rsi': df['rsi'].iloc[-1],
            'ema_50': df['ema_50'].iloc[-1],
            'macd': df['macd'].iloc[-1],
            'macd_signal': df['signal'].iloc[-1],
            'close': df['close'].iloc[-1]
        }
        
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
        
        # 4. SNIPER (Executor)
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

def update_status_db(msg):
    try:
        db.table("bot_config").upsert({"key": "BOT_STATUS_DETAIL", "value": msg}).execute()
        print(f"Status: {msg}")
    except: pass

def run_farming_cycle():
    """PHASE 1: FARMING (Data Gathering) - Runs occasionally"""
    global last_heartbeat
    log_activity("System", "🚜 Starting Farming Cycle (Data Gathering)...")
    update_status_db("🚜 Farming Mode: Initializing...")
    
    last_heartbeat = time.time()
    
    # 1. Radar Scan (Wide Range)
    # Scan top candidates in Farming Mode
    update_status_db("📡 Radar: Scanning Market (Wide Range)...")
    
    # Start Farming Session Log
    farm_id = None
    try:
        f_res = db.table("farming_history").insert({"status": "IN_PROGRESS"}).execute()
        farm_id = f_res.data[0]['id']
    except: pass
    
    candidates_raw = radar.scan_market(callback=update_status_db, logger=log_activity) 
    
    last_heartbeat = time.time()

    # 2. Head Hunter Screen
    update_status_db("📋 HeadHunter: Analyzing Fundamentals...")
    candidates = head_hunter.screen_market(candidates_raw)
    
    if not candidates:
        msg = "Farming yielded no crops (candidates). Retrying next cycle."
        log_activity("System", msg, "WARNING")
        update_status_db(f"❌ {msg}")
        
        # Update Log as Failed
        if farm_id:
             try: db.table("farming_history").update({"status": "FAILED", "logs": "No candidates found"}).eq("id", farm_id).execute()
             except: pass
        return
        
    # 3. Save "Harvest" to DB for Sniper
    # Store list of symbols to trade
    try:
        symbols = [c['symbol'] for c in candidates]
        import json
        db.table("bot_config").upsert({"key": "ACTIVE_CANDIDATES", "value": json.dumps(symbols)}).execute()
        db.table("bot_config").upsert({"key": "LAST_FARM_TIME", "value": str(time.time())}).execute()
        
        # Complete Farming Log
        if farm_id:
             try: 
                 db.table("farming_history").update({
                     "status": "COMPLETED", 
                     "end_time": "now()",
                     "candidates_found": len(symbols),
                     "logs": f"Farmed {len(symbols)} coins."
                 }).eq("id", farm_id).execute()
             except: pass
        
        log_activity("System", f"🌾 Harvest Complete. {len(symbols)} coins ready for Sniper.", "SUCCESS")
        update_status_db(f"✅ Farmed {len(symbols)} coins. Switch to Sniper.")
    except Exception as e:
        log_activity("System", f"Harvest Save Error: {e}", "ERROR")

def run_trading_cycle():
    """PHASE 2: SNIPER (Execution) - Runs frequently"""
    global last_heartbeat
    last_heartbeat = time.time()
    
    # 1. Check if we need to Farm first
    try:
        last_farm = db.table("bot_config").select("value").eq("key", "LAST_FARM_TIME").execute()
        active_list = db.table("bot_config").select("value").eq("key", "ACTIVE_CANDIDATES").execute()
        
        should_farm = False
        if not last_farm.data or not active_list.data:
            should_farm = True
        else:
            # Dynamic Farming Interval (User Request)
            try:
                interval_cfg = db.table("bot_config").select("value").eq("key", "FARMING_INTERVAL_HOURS").execute()
                interval_hours = float(interval_cfg.data[0]['value']) if interval_cfg.data else 12.0
            except: interval_hours = 12.0
            
            interval_seconds = interval_hours * 3600
            
            elapsed = time.time() - float(last_farm.data[0]['value'])
            if elapsed > interval_seconds: 
                should_farm = True
                
        if should_farm:
            run_farming_cycle()
            return # Skip trading this cycle, wait for next heartbeat to trade
            
        # 2. Load Candidates
        import json
        candidates_str = active_list.data[0]['value'].replace("'", '"')
        candidates = json.loads(candidates_str)
        
        if not candidates:
             run_farming_cycle()
             return

        # 3. Snipe (Process)
        # Load timeframe
        try:
            tf = db.table("bot_config").select("value").eq("key", "TIMEFRAME").execute()
            timeframe = str(tf.data[0]['value']).replace('"', '')
        except: timeframe = "1h"

        # Calculate Remaining Time dynamically
        remaining_seconds = interval_seconds - (time.time() - float(last_farm.data[0]['value']))
        next_farm_in = max(0, int(remaining_seconds / 3600))
        
        update_status_db(f"🔫 Sniper Mode: Hunting {len(candidates)} pairs (Next Farm: {next_farm_in}h)")
        
        for i, symbol in enumerate(candidates):
            last_heartbeat = time.time()
            process_pair(symbol, timeframe)
            time.sleep(1)
            
    except Exception as e:
        print(f"Trading Cycle Error: {e}")
        # If DB read fails, retry later
        time.sleep(5)

def start_watchdog():
    """Monitors system heartbeat and kills process if stuck"""
    global last_heartbeat
    print("🐕 Watchdog Started")
    while True:
        time.sleep(60)
        # If no heartbeat for 5 minutes (300s), kill the process
        if time.time() - last_heartbeat > 300:
            msg = f"Watchdog: System Frozen for {time.time() - last_heartbeat:.0f}s. RESTARTING CONTAINER..."
            print(f"💀 {msg}")
            log_activity("System", msg, "ERROR")
            os._exit(1) # Force Kill
        
        # Save Heartbeat to DB for Dashboard Visibility
        try:
            db.table("bot_config").upsert({"key": "LAST_HEARTBEAT", "value": str(time.time())}).execute()
        except Exception as e:
            print(f"Heartbeat DB Error: {e}")

def start():
    global last_heartbeat
    try:
        log_activity("System", "🚀 Zenith Bot Started (6-Role Architecture)", "SUCCESS")
        
        # Start Watchdog
        wd = threading.Thread(target=start_watchdog, daemon=True)
        wd.start()

        # Init heartbeat
        last_heartbeat = time.time()
        
        # --- IMMEDIATE FEEDBACK FOR USER ---
        # Write "I am Alive" signal to DB immediately so Dashboard turns GREEN
        try:
             db.table("bot_config").upsert({"key": "LAST_HEARTBEAT", "value": str(time.time())}).execute()
             print("💓 Heartbeat Initialized in DB")
        except: pass
        
        # Run once immediately
        run_trading_cycle()
        
        # Schedule - Check 'Sniper' loop every 2 minutes
        # Logic inside Sniper will determine if Farming is needed
        schedule.every(2).minutes.do(run_trading_cycle) 
        
        print("Bot scheduled for 2-minute Sniper cycles.")
        
        while True:
            try:
                # Pulse check logic is now distributed inside the heavy tasks
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
