import time
import json
import schedule
import threading
import os
import pandas as pd
from src.database import get_db

# --- IMPORT NEW ROLES ---
from src.roles.job_screener import HeadHunter
from src.roles.job_price import PriceSpy
from src.roles.job_scout import Radar
from src.roles.job_analysis import Strategist, Judge
from src.roles.job_executor import SniperExecutor
from src.roles.job_wallet import WalletSync

# --- IMPORT SESSION MANAGER ---
from src.session_manager import (
    get_active_session,
    create_session,
    take_balance_snapshot
)

# --- IMPORT CAPITAL MANAGER ---
from src.capital_manager import get_available_trading_balance

# Thread-safe heartbeat tracking
_heartbeat_lock = threading.Lock()
_last_heartbeat = time.time()

def get_heartbeat():
    with _heartbeat_lock:
        return _last_heartbeat

def set_heartbeat():
    global _last_heartbeat
    with _heartbeat_lock:
        _last_heartbeat = time.time()

# Initialize Team
db = get_db()
head_hunter = HeadHunter(db) # Pass DB for Config/Fundamental Data
price_spy = PriceSpy()
radar = Radar(price_spy) # Radar uses PriceSpy

# Initialize Strategist early to select AI model
print("🧠 Initializing AI Strategist...")
strategist = Strategist()
print("✅ Strategist ready")

judge = Judge()
sniper = SniperExecutor(spy_instance=price_spy)
wallet_sync = WalletSync(db, sniper.exchange)  # Use sniper's exchange instance

TIMEFRAME = "1h"

def is_bot_stopped():
    """Check if the bot has been stopped via dashboard Emergency Stop."""
    try:
        status = db.table("bot_config").select("value").eq("key", "BOT_STATUS").execute()
        if status.data:
            val = str(status.data[0]['value']).replace('"', '').strip()
            return val == "STOPPED"
    except Exception as e:
        print(f"BOT_STATUS check error: {e}")
    return False

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
    if is_bot_stopped():
        print(f"⛔ Bot STOPPED. Skipping {pair}.")
        return
    try:
        # 1. SPY A (Price)
        print(f"--- 1. SPY A: Fetching Price for {pair} ({timeframe}) ---")
        log_activity("Spy", f"🕵️ Scanning {pair} ({timeframe}) market...")
        df = price_spy.fetch_ohlcv(pair, timeframe)
        if df is None: 
            print(f"❌ Data Fetch Failed for {pair}")
            return
            
        df = price_spy.calculate_indicators(df)
        if df is None or df.empty:
            print(f"❌ Indicator Calculation Failed for {pair}")
            return

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

        # Send only relevant columns to reduce prompt size and avoid timestamp/NaN issues
        tech_cols = ['close', 'open', 'high', 'low', 'volume', 'rsi', 'macd', 'signal', 'ema_20', 'ema_50', 'atr']
        available_cols = [c for c in tech_cols if c in df.columns]
        tech_snapshot = df[available_cols].tail(5).fillna(0).round(6).to_dict()
        analysis = strategist.analyze_market(None, pair, tech_snapshot)
        if not analysis: 
            print("❌ AI Analysis Failed")
            return
        
        # LOG AI SUMMARY
        log_activity("Strategist", f"[{pair}] Sentiment: {analysis.get('sentiment_score')} | Confidence: {analysis.get('confidence')}%")

        # 3. JUDGE (Rules)
        print("3. Judge Evaluate...")

        # FETCH REAL BALANCE based on Mode (with capital protection)
        try:
            mode_cfg = db.table("bot_config").select("value").eq("key", "TRADING_MODE").execute()
            mode = str(mode_cfg.data[0]['value']).replace('"', '').strip() if mode_cfg.data else "PAPER"
        except Exception as e:
            print(f"Mode fetch error: {e}")
            mode = "PAPER"

        if mode == "PAPER":
            try:
                sim_wallet = db.table("simulation_portfolio").select("balance").eq("id", 1).execute()
                actual_balance = float(sim_wallet.data[0]['balance']) if sim_wallet.data else 1000.0
            except Exception as e:
                print(f"Sim wallet fetch error: {e}")
                actual_balance = 1000.0
        else:
            try:
                # LIVE Mode: Fetch real USDT balance
                bal_data = price_spy.get_account_balance()
                actual_balance = bal_data['total'].get('USDT', 0.0) if bal_data else 0.0
            except Exception as e:
                print(f"Live balance fetch error: {e}")
                actual_balance = 0.0

        # Apply capital protection limits (bot only uses trading_capital, not full balance)
        balance = get_available_trading_balance(mode=mode, actual_balance=actual_balance)
        
        # Convert AI output to needed format
        ai_data = {'confidence': analysis.get('confidence'), 'recommendation': analysis.get('recommendation')}
        tech_data = {
            'rsi': df['rsi'].iloc[-1],
            'ema_50': df['ema_50'].iloc[-1],
            'macd': df['macd'].iloc[-1],
            'macd_signal': df['signal'].iloc[-1],
            'close': df['close'].iloc[-1]
        }
        
        is_sim = (mode == "PAPER")
        ai_rec = analysis.get('recommendation', 'UNKNOWN')

        # Skip non-actionable signals entirely (no DB write, no execution)
        if ai_rec in ['WAIT', 'HOLD']:
            print(f"   - AI Recommendation: {ai_rec} -- Skipping (non-actionable)")
            return

        verdict = judge.evaluate(ai_data, tech_data, balance, is_sim=is_sim, asset_id=asset_id)
        print(f"   - AI Recommendation: {ai_rec} (Confidence: {ai_data['confidence']}%)")
        print(f"   - Judge Verdict: {verdict.decision} -> {verdict.reason}")

        # Log Signal to DB (only BUY/SELL, not WAIT/HOLD)
        current_price = float(df['close'].iloc[-1])
        current_atr = float(df['atr'].iloc[-1]) if 'atr' in df.columns and not pd.isna(df['atr'].iloc[-1]) else 0.0

        signal_data = {
            "asset_id": asset_id,
            "signal_type": ai_rec,
            "entry_target": current_price,
            "entry_atr": current_atr,
            "status": "PENDING" if verdict.decision == "APPROVED" else "REJECTED",
            "judge_reason": verdict.reason,
            "is_sim": is_sim
        }
        signal_entry = db.table("trade_signals").insert(signal_data).execute()
        
        # 4. SNIPER (Executor)
        if verdict.decision == "APPROVED":
            print("4. Sniper Firing!")
            log_activity("Sniper", f"🔫 Executing {pair}...", "WARNING")
            # Use full signal object
            full_signal = signal_entry.data[0]
            full_signal['assets'] = {'symbol': pair} # Manual hydrate for simplicity
            full_signal['order_size'] = verdict.size  # USDT amount from Judge

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
    except Exception as e:
        print(f"Status DB update error: {e}")

def check_trailing_stops():
    """Check all open positions for trailing stop triggers."""
    try:
        # Read config
        trail_enabled_res = db.table("bot_config").select("value").eq("key", "TRAILING_STOP_ENABLED").execute()
        if not trail_enabled_res.data or str(trail_enabled_res.data[0]['value']).replace('"', '').strip().lower() != 'true':
            return

        # ATR-based or Fixed % trailing stop
        use_atr_res = db.table("bot_config").select("value").eq("key", "TRAILING_STOP_USE_ATR").execute()
        use_atr = str(use_atr_res.data[0]['value']).replace('"', '').strip().lower() == 'true' if use_atr_res.data else False
        
        # Config for Fixed % mode
        trail_pct_res = db.table("bot_config").select("value").eq("key", "TRAILING_STOP_PCT").execute()
        trail_pct = float(str(trail_pct_res.data[0]['value']).replace('"', '').strip()) / 100 if trail_pct_res.data else 0.03
        
        # Config for ATR mode
        atr_multiplier_res = db.table("bot_config").select("value").eq("key", "TRAILING_STOP_ATR_MULTIPLIER").execute()
        atr_multiplier = float(str(atr_multiplier_res.data[0]['value']).replace('"', '').strip()) if atr_multiplier_res.data else 2.0

        min_profit_res = db.table("bot_config").select("value").eq("key", "MIN_PROFIT_TO_TRAIL_PCT").execute()
        min_profit_pct = float(str(min_profit_res.data[0]['value']).replace('"', '').strip()) / 100 if min_profit_res.data else 0.01

        # Fetch ALL open positions (both PAPER and LIVE)
        positions = db.table("positions").select("*, assets(symbol)").eq("is_open", True).execute()
        if not positions.data:
            return

        for pos in positions.data:
            symbol = pos['assets']['symbol'] if pos.get('assets') else None
            if not symbol:
                continue

            entry_price = float(pos['entry_avg'])
            highest = float(pos.get('highest_price_seen') or entry_price)

            # Fetch current price
            try:
                ticker = price_spy.exchange.fetch_ticker(symbol)
                current_price = ticker['last']
            except Exception as e:
                print(f"Trailing stop: Failed to fetch price for {symbol}: {e}")
                continue

            # Update highest price seen
            if current_price > highest:
                highest = current_price
                db.table("positions").update({"highest_price_seen": highest}).eq("id", pos['id']).execute()

            # Check if min profit threshold reached
            profit_pct = (highest - entry_price) / entry_price
            if profit_pct < min_profit_pct:
                continue  # Not enough profit to activate trailing stop

            # Calculate trailing stop price (ATR-based or Fixed %)
            if use_atr:
                # ATR-based: More dynamic, adjusts to volatility
                position_atr = pos.get('entry_atr')  # ATR at entry time
                if position_atr and float(position_atr) > 0:
                    atr_value = float(position_atr)
                    # Trail by ATR * multiplier below highest price
                    trail_distance = atr_value * atr_multiplier
                    trail_price = highest - trail_distance
                    print(f"[ATR Trail] {symbol}: ATR={atr_value:.2f}, Multiplier={atr_multiplier}, Distance=${trail_distance:.2f}")
                else:
                    # Fallback to fixed % if no ATR data
                    trail_price = highest * (1 - trail_pct)
                    print(f"[Fixed Trail Fallback] {symbol}: No ATR data, using {trail_pct*100}%")
            else:
                # Fixed percentage mode (original behavior)
                trail_price = highest * (1 - trail_pct)
                print(f"[Fixed Trail] {symbol}: {trail_pct*100}% below peak")

            # Update trailing_stop_price in DB (for dashboard visibility)
            db.table("positions").update({"trailing_stop_price": trail_price}).eq("id", pos['id']).execute()

            # TRIGGER: Price dropped below trailing stop
            if current_price <= trail_price:
                is_sim = pos.get('is_sim', True)
                log_activity("System", f"Trailing Stop triggered for {symbol}! Price ${current_price:,.2f} < Stop ${trail_price:,.2f}", "WARNING")

                # Create a SELL signal and execute
                signal_data = {
                    "asset_id": pos['asset_id'],
                    "signal_type": "SELL",
                    "entry_target": current_price,
                    "status": "PENDING",
                    "judge_reason": f"Trailing Stop: price ${current_price:,.2f} < stop ${trail_price:,.2f} (peak ${highest:,.2f})",
                    "is_sim": is_sim
                }
                signal_entry = db.table("trade_signals").insert(signal_data).execute()
                full_signal = signal_entry.data[0]
                full_signal['assets'] = {'symbol': symbol}
                full_signal['order_size'] = 0  # Not used for SELL (uses position qty)

                success = sniper.execute_order(full_signal)
                if success:
                    log_activity("Sniper", f"Trailing Stop SELL executed for {symbol}", "SUCCESS")
                else:
                    log_activity("Sniper", f"Trailing Stop SELL failed for {symbol}", "ERROR")

            time.sleep(0.15)  # Rate limit between ticker fetches
    except Exception as e:
        print(f"Trailing Stop Check Error: {e}")

def run_farming_cycle():
    """PHASE 1: FARMING (Data Gathering) - Runs occasionally"""
    log_activity("System", "🚜 Starting Farming Cycle (Data Gathering)...")
    update_status_db("🚜 Farming Mode: Initializing...")

    set_heartbeat()
    
    # 1. Radar Scan (Wide Range)
    # Scan top candidates in Farming Mode
    update_status_db("📡 Radar: Scanning Market (Wide Range)...")
    
    # Start Farming Session Log
    farm_id = None
    try:
        f_res = db.table("farming_history").insert({"status": "IN_PROGRESS"}).execute()
        farm_id = f_res.data[0]['id']
    except Exception as e:
        print(f"Farming history insert error: {e}")
    
    candidates_raw = radar.scan_market(callback=update_status_db, logger=log_activity)

    set_heartbeat()

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
             except Exception as e: print(f"Farming history update error: {e}")
        return
        
    # 3. Save "Harvest" to DB for Sniper
    # Store list of symbols to trade
    try:
        symbols = [c['symbol'] for c in candidates]
        db.table("bot_config").upsert({"key": "ACTIVE_CANDIDATES", "value": json.dumps(symbols)}).execute()
        db.table("bot_config").upsert({"key": "LAST_FARM_TIME", "value": str(time.time())}).execute()
        
        # Complete Farming Log
        if farm_id:
             try:
                 from datetime import datetime, timezone
                 db.table("farming_history").update({
                     "status": "COMPLETED",
                     "end_time": datetime.now(timezone.utc).isoformat(),
                     "candidates_found": len(symbols),
                     "logs": f"Farmed {len(symbols)} coins."
                 }).eq("id", farm_id).execute()
             except Exception as e: print(f"Farming history complete error: {e}")
        
        log_activity("System", f"🌾 Harvest Complete. {len(symbols)} coins ready for Sniper.", "SUCCESS")
        update_status_db(f"✅ Farmed {len(symbols)} coins. Switch to Sniper.")
    except Exception as e:
        log_activity("System", f"Harvest Save Error: {e}", "ERROR")

def run_trading_cycle():
    """PHASE 2: SNIPER (Execution) - Runs frequently"""
    set_heartbeat()

    if is_bot_stopped():
        log_activity("System", "⛔ Bot is STOPPED. Skipping trading cycle.", "WARNING")
        return

    # 0. Check trailing stops BEFORE processing new signals
    check_trailing_stops()

    # 0b. Take balance snapshots for both modes (for drawdown tracking)
    try:
        # Get current mode
        mode_cfg = db.table("bot_config").select("value").eq("key", "TRADING_MODE").execute()
        current_mode = str(mode_cfg.data[0]['value']).replace('"', '').strip() if mode_cfg.data else "PAPER"

        # Take snapshot for current active mode
        session = get_active_session(mode=current_mode)
        if session:
            if current_mode == "PAPER":
                sim_wallet = db.table("simulation_portfolio").select("balance").eq("id", 1).execute()
                balance = float(sim_wallet.data[0]['balance']) if sim_wallet.data else 1000.0
            else:
                bal_data = price_spy.get_account_balance()
                balance = bal_data['total'].get('USDT', 0.0) if bal_data else 0.0

            # Calculate unrealized P&L from open positions
            unrealized_pnl = 0.0
            open_pos = db.table("positions").select("*, assets(symbol)").eq("is_open", True).eq("is_sim", (current_mode == "PAPER")).execute()
            if open_pos.data:
                for pos in open_pos.data:
                    try:
                        symbol = pos['assets']['symbol'] if pos['assets'] else None
                        if symbol:
                            ticker = price_spy.exchange.fetch_ticker(symbol)
                            curr_price = ticker['last']
                            unrealized_pnl += (curr_price - float(pos['entry_avg'])) * float(pos['quantity'])
                    except:
                        pass

            take_balance_snapshot(session['id'], balance, unrealized_pnl)
    except Exception as e:
        print(f"Balance snapshot error: {e}")

    # 1. Check if we need to Farm first
    try:
        last_farm = db.table("bot_config").select("value").eq("key", "LAST_FARM_TIME").execute()
        active_list = db.table("bot_config").select("value").eq("key", "ACTIVE_CANDIDATES").execute()
        
        # Dynamic Farming Interval (User Request)
        try:
            interval_cfg = db.table("bot_config").select("value").eq("key", "FARMING_INTERVAL_HOURS").execute()
            interval_hours = float(interval_cfg.data[0]['value']) if interval_cfg.data else 12.0
        except Exception as e:
            print(f"Farming interval config error: {e}")
            interval_hours = 12.0
        interval_seconds = interval_hours * 3600

        should_farm = False
        if not last_farm.data or not active_list.data:
            should_farm = True
        else:
            elapsed = time.time() - float(last_farm.data[0]['value'])
            if elapsed > interval_seconds:
                should_farm = True
                
        if should_farm:
            run_farming_cycle()
            return # Skip trading this cycle, wait for next heartbeat to trade
            
        # 2. Load Candidates
        candidates_str = active_list.data[0]['value'].replace("'", '"')
        candidates = json.loads(candidates_str)

        if not candidates:
             run_farming_cycle()
             return

        # 2b. Include symbols from open positions to prevent orphaned holdings
        try:
            mode_cfg = db.table("bot_config").select("value").eq("key", "TRADING_MODE").execute()
            current_mode = str(mode_cfg.data[0]['value']).replace('"', '').strip() if mode_cfg.data else "PAPER"
            is_sim_mode = (current_mode == "PAPER")
            open_positions = db.table("positions").select("asset_id, assets(symbol)")\
                .eq("is_open", True).eq("is_sim", is_sim_mode).execute()
            if open_positions.data:
                held_symbols = set()
                for pos in open_positions.data:
                    sym = pos.get('assets', {}).get('symbol') if pos.get('assets') else None
                    if sym:
                        held_symbols.add(sym)
                # Add held symbols not already in candidates
                candidate_set = set(candidates)
                for sym in held_symbols:
                    if sym not in candidate_set:
                        candidates.append(sym)
                        print(f"[SafeGuard] Added held position {sym} to candidates (not in farm list)")
        except Exception as e:
            print(f"Orphan position check error: {e}")

        # 3. Snipe (Process)
        # Load timeframe
        try:
            tf = db.table("bot_config").select("value").eq("key", "TIMEFRAME").execute()
            timeframe = str(tf.data[0]['value']).replace('"', '')
        except Exception as e:
            print(f"Timeframe config error: {e}")
            timeframe = "1h"

        # Calculate Remaining Time dynamically
        remaining_seconds = interval_seconds - (time.time() - float(last_farm.data[0]['value']))
        next_farm_in = max(0, int(remaining_seconds / 3600))
        
        update_status_db(f"🔫 Sniper Mode: Hunting {len(candidates)} pairs (Next Farm: {next_farm_in}h)")
        
        for i, symbol in enumerate(candidates):
            set_heartbeat()
            process_pair(symbol, timeframe)
            time.sleep(1)
            
    except Exception as e:
        print(f"Trading Cycle Error: {e}")
        # If DB read fails, retry later
        time.sleep(5)

def start_watchdog():
    """Monitors system heartbeat and kills process if stuck"""
    print("🐕 Watchdog Started")
    while True:
        time.sleep(60)
        # If no heartbeat for 5 minutes (300s), kill the process
        elapsed = time.time() - get_heartbeat()
        if elapsed > 300:
            msg = f"Watchdog: System Frozen for {elapsed:.0f}s. RESTARTING CONTAINER..."
            print(f"💀 {msg}")
            log_activity("System", msg, "ERROR")
            os._exit(1) # Force Kill
        
        # Save Heartbeat to DB for Dashboard Visibility
        try:
            db.table("bot_config").upsert({"key": "LAST_HEARTBEAT", "value": str(time.time())}).execute()
        except Exception as e:
            print(f"Heartbeat DB Error: {e}")

def start():
    try:
        log_activity("System", "🚀 Zenith Bot Started (6-Role Architecture)", "SUCCESS")

        # Start Watchdog
        wd = threading.Thread(target=start_watchdog, daemon=True)
        wd.start()

        # Init heartbeat
        set_heartbeat()
        
        # --- IMMEDIATE FEEDBACK FOR USER ---
        # Write "I am Alive" signal to DB immediately so Dashboard turns GREEN
        try:
             db.table("bot_config").upsert({"key": "LAST_HEARTBEAT", "value": str(time.time())}).execute()
             print("💓 Heartbeat Initialized in DB")
             
             # Set MODE based on config
             mode_cfg = db.table("bot_config").select("value").eq("key", "TRADING_MODE").execute()
             if mode_cfg.data:
                 mode = str(mode_cfg.data[0]['value']).replace('"', '').strip().upper()
             else:
                 mode = "SNIPER"  # Default mode
             
             db.table("bot_config").upsert({"key": "MODE", "value": mode}).execute()
             print(f"🎯 MODE set to: {mode}")
        except Exception as e:
            print(f"Heartbeat/Mode init error: {e}")
        
        # --- IMMEDIATE ACTIONS ---
        
        # 1. Sync Wallet FIRST (Fast & Important for UI)
        print("💰 Syncing Wallet Data...")
        try:
            wallet_sync.sync_wallet()
            print("✅ Wallet Sync Complete")
        except Exception as e:
            log_activity("WalletSync", f"Initial sync failed: {e}", "ERROR")

        # 1b. Initialize Trading Sessions
        print("📊 Initializing Trading Sessions...")
        try:
            # Check/create session for PAPER mode
            paper_session = get_active_session(mode='PAPER')
            if not paper_session:
                # Get current simulation balance
                sim_wallet = db.table("simulation_portfolio").select("balance").eq("id", 1).execute()
                start_balance = float(sim_wallet.data[0]['balance']) if sim_wallet.data else 1000.0
                create_session(mode='PAPER', start_balance=start_balance, session_name="Paper Session (Auto-Start)")
                print("✅ Created PAPER session")
            else:
                print(f"✅ Using existing PAPER session: {paper_session['session_name']}")

            # Check/create session for LIVE mode
            live_session = get_active_session(mode='LIVE')
            if not live_session:
                # Get current live balance
                try:
                    bal_data = price_spy.get_account_balance()
                    start_balance = bal_data['total'].get('USDT', 1000.0) if bal_data else 1000.0
                except:
                    start_balance = 1000.0
                create_session(mode='LIVE', start_balance=start_balance, session_name="Live Session (Auto-Start)")
                print("✅ Created LIVE session")
            else:
                print(f"✅ Using existing LIVE session: {live_session['session_name']}")
        except Exception as e:
            log_activity("System", f"Session initialization failed: {e}", "ERROR")

        # 2. Run Trading Cycle (Can take time)
        print("🚀 Starting First Trading Cycle...")
        try:
            run_trading_cycle()
        except Exception as e:
             # Log but DO NOT CRASH. The scheduler will try again later.
             print(f"❌ Initial Trading Cycle Failed: {e}")
             log_activity("System", f"Initial Trading Cycle Failed: {e}", "ERROR")

        # Load trading cycle interval from DB (default 2 minutes)
        try:
            cycle_cfg = db.table("bot_config").select("value").eq("key", "TRADING_CYCLE_MINUTES").execute()
            cycle_minutes = int(float(cycle_cfg.data[0]['value'])) if cycle_cfg.data else 2
        except Exception:
            cycle_minutes = 2

        schedule.every(cycle_minutes).minutes.do(run_trading_cycle)
        
        # Schedule wallet sync every 5 minutes
        schedule.every(5).minutes.do(wallet_sync.sync_wallet)

        print(f"Bot scheduled for {cycle_minutes}-minute Sniper cycles.")
        
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
        except Exception:
            print(f"Fatal: {e}")

if __name__ == "__main__":
    start()
