import time
import json
import schedule
import threading
import os
import pandas as pd
from src.database import get_db
from src.ai.tiering import TieredAIDecisionEngine
from src.telemetry.tracker import TelemetryTracker

# --- IMPORT NEW ROLES ---
from src.roles.job_screener import HeadHunter
from src.roles.job_price import PriceSpy
from src.roles.job_scout import Radar
from src.roles.job_analysis import Strategist, Judge, TradeDecision
from src.roles.job_executor import SniperExecutor
from src.roles.job_wallet import WalletSync
from src.roles.signal_scoring import SignalScorer

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
tiered_ai_engine = TieredAIDecisionEngine(strategist=strategist)
telemetry_tracker = TelemetryTracker(db=db)
signal_scorer = SignalScorer(db=db)

judge = Judge()
sniper = SniperExecutor(spy_instance=price_spy)
wallet_sync = WalletSync(db, sniper.exchange)  # Use sniper's exchange instance

TIMEFRAME = "1h"


def get_config_value(key, default=None):
    try:
        result = db.table("bot_config").select("value").eq("key", key).limit(1).execute()
        if result.data:
            raw = result.data[0].get("value")
            if isinstance(raw, str):
                return raw.replace('"', "").strip()
            return raw
    except Exception:
        pass
    return default


def _to_float_safe(raw, default=0.0):
    try:
        if raw is None:
            return default
        if pd.isna(raw):
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def _infer_asset_class(symbol, candidate_type=None):
    normalized = str(candidate_type or "").strip().lower()
    if normalized in {"crypto", "stock", "gold", "silver"}:
        return normalized
    sym = str(symbol or "").upper().strip()
    if "/" in sym:
        return "crypto"
    if "XAU" in sym or "GOLD" in sym:
        return "gold"
    if "XAG" in sym or "SILVER" in sym:
        return "silver"
    return "stock" if sym else "other"


def persist_universe_snapshot(snapshot_id, candidates, stage="farming"):
    if not candidates:
        return
    rows = []
    include_reason = (
        f"{stage}; universe={getattr(head_hunter, 'universe', 'TOP_100')}; "
        f"whitelist_policy={getattr(head_hunter, 'whitelist_policy', 'RELAXED')}"
    )
    for idx, candidate in enumerate(candidates, start=1):
        if isinstance(candidate, str):
            symbol = candidate.strip().upper()
            row = {}
        elif isinstance(candidate, dict):
            symbol = str(candidate.get("symbol", "")).upper().strip()
            row = candidate
        else:
            continue
        if not symbol:
            continue

        rows.append(
            {
                "symbol": symbol,
                "asset_class": _infer_asset_class(symbol=symbol, candidate_type=row.get("candidate_type")),
                "rank": int(row.get("screener_rank") or idx),
                "source": str(row.get("source") or "radar_scan"),
                "volume": _to_float_safe(row.get("volume"), default=0.0),
                "status": str(row.get("status") or "NEUTRAL").upper(),
                "whitelist_pass": bool(row.get("whitelist_pass", False)),
                "inclusion_reason": include_reason,
                "metadata": {
                    "volume_threshold": _to_float_safe(row.get("volume_threshold"), default=0.0),
                    "stage": stage,
                },
            }
        )

    if not rows:
        return
    result = telemetry_tracker.track_universe_snapshot_rows(snapshot_id=snapshot_id, rows=rows)
    if not result.get("ok"):
        print(f"Universe snapshot save error: {result.get('error')}")
        return

    try:
        db.table("bot_config").upsert({"key": "LAST_UNIVERSE_SNAPSHOT_ID", "value": str(snapshot_id)}).execute()
    except Exception as config_error:
        print(f"Universe snapshot config update error: {config_error}")


def is_ai_tiering_enabled():
    raw = str(get_config_value("ENABLE_AI_TIERING", "false")).lower()
    return raw in ("1", "true", "yes")

def get_bot_runtime_status():
    """Read runtime status from DB; defaults to ACTIVE when unavailable."""
    try:
        status = db.table("bot_config").select("value").eq("key", "BOT_STATUS").execute()
        if status.data:
            val = str(status.data[0]['value']).replace('"', '').strip().upper()
            if val:
                return val
    except Exception as e:
        print(f"BOT_STATUS check error: {e}")
    return "ACTIVE"


def is_trading_halted():
    return get_bot_runtime_status() in {"STOPPED", "PAUSED"}

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

def process_pair(pair, timeframe, intent="ENTRY"):
    """
    Encapsulated logic for a single trading pair with explicit INTENT.
    :param intent: "ENTRY" (Look for BUY) or "EXIT" (Look for SELL)
    """
    runtime_status = get_bot_runtime_status()
    if runtime_status in {"STOPPED", "PAUSED"}:
        print(f"⛔ Bot {runtime_status}. Skipping {pair}.")
        return
    try:
        # 1. SPY A (Price)
        print(f"--- 1. SPY A: Fetching Price for {pair} ({timeframe}) [Intent: {intent}] ---")
        # log_activity("Spy", f"🕵️ Scanning {pair} ({timeframe}) market...") # Reduce log noise
        
        # Ensure enough candles for EMA200/downtrend detection
        df = price_spy.fetch_ohlcv(pair, timeframe, limit=250)
        if df is None: 
            print(f"❌ Data Fetch Failed for {pair}")
            return
            
        df = price_spy.calculate_indicators(df)
        if df is None or df.empty:
            print(f"❌ Indicator Calculation Failed for {pair}")
            return

        # Calculate Market Trend (for downtrend protection)
        trend_data = price_spy.detect_market_trend(df)
        print(f"   - Market Trend: {trend_data['trend']} (Strength: {trend_data['strength']:.0f}%, Confidence: {trend_data['confidence']:.0f}%)")

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
        tech_cols = [
            'close', 'open', 'high', 'low', 'volume',
            'rsi', 'macd', 'signal',
            'ema_20', 'ema_50', 'ema_200',  # Add EMA 200
            'atr',
            'adx', 'dmp', 'dmn',  # Add ADX components
            'ema_50_slope', 'price_position_score'  # Add derived indicators
        ]
        available_cols = [c for c in tech_cols if c in df.columns]
        tech_snapshot = df[available_cols].tail(5).fillna(0).round(6).to_dict()

        tier_run_id = None
        analysis = None

        # Call AI with explicit INTENT (P5 tiering optional)
        if is_ai_tiering_enabled():
            tier_result = tiered_ai_engine.evaluate(
                symbol=pair,
                tech_snapshot=tech_snapshot,
                intent=intent,
                config=judge.config,
            )
            tier_run_id = tier_result["run_id"]
            analysis = tier_result["final"]

            # P4: persist all 3 tier outputs for replay
            try:
                for row in tiered_ai_engine.to_telemetry_records(
                    result=tier_result, symbol=pair, timeframe=timeframe
                ):
                    telemetry_tracker.track_ai_decision(
                        run_id=row["run_id"],
                        symbol=row["symbol"],
                        timeframe=row["timeframe"],
                        tier=row["tier"],
                        model=row["model"],
                        prompt=row["prompt"],
                        input_payload=row["input_payload"],
                        output_json=row["output_json"],
                        confidence=row["confidence"],
                        latency_ms=row["latency_ms"],
                    )
            except Exception as telemetry_error:
                print(f"Telemetry tier save error: {telemetry_error}")
        else:
            analysis = strategist.analyze_market(None, pair, tech_snapshot, intent=intent)
            tier_run_id = f"{pair}-{int(time.time())}"
            # P4: persist single-tier decision (legacy path)
            try:
                if analysis:
                    telemetry_tracker.track_ai_decision(
                        run_id=tier_run_id,
                        symbol=pair,
                        timeframe=timeframe,
                        tier="TIER_2_DECISION",
                        model=str(get_config_value("AI_MODEL", "GEMINI")),
                        prompt={"type": "legacy"},
                        input_payload=tech_snapshot,
                        output_json=analysis,
                        confidence=float(analysis.get("confidence", 0)),
                        latency_ms=0,
                    )
            except Exception as telemetry_error:
                print(f"Telemetry decision save error: {telemetry_error}")

        if not analysis: 
            print("❌ AI Analysis Failed")
            return
        
        # LOG AI SUMMARY
        log_activity("Strategist", f"[{pair}] {intent} Analysis | Rec: {analysis.get('recommendation')} | Conf: {analysis.get('confidence')}%")

        # 3. JUDGE (Rules)
        print("3. Judge Evaluate...")

        # FETCH REAL BALANCE based on Mode (with capital protection)
        try:
            mode_cfg = db.table("bot_config").select("value").eq("key", "TRADING_MODE").execute()
            mode = str(mode_cfg.data[0]['value']).replace('"', '').strip() if mode_cfg.data else "PAPER"
        except Exception as e:
            # print(f"Mode fetch error: {e}")
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
        ai_data = {
            'confidence': analysis.get('confidence'),
            'recommendation': analysis.get('recommendation'),
            'sentiment_score': analysis.get('sentiment_score'),
        }
        latest_row = df.iloc[-1]
        current_price = _to_float_safe(latest_row.get('close'), default=0.0)
        base_volume = _to_float_safe(latest_row.get('volume'), default=0.0)
        quote_volume = current_price * base_volume if current_price > 0 and base_volume > 0 else 0.0
        current_atr = _to_float_safe(latest_row.get('atr'), default=0.0)

        tech_data = {
            'rsi': _to_float_safe(latest_row.get('rsi'), default=50.0),
            'ema_20': _to_float_safe(latest_row.get('ema_20'), default=0.0),
            'ema_50': _to_float_safe(latest_row.get('ema_50'), default=0.0),
            'ema_200': _to_float_safe(latest_row.get('ema_200'), default=0.0),
            'macd': _to_float_safe(latest_row.get('macd'), default=0.0),
            'macd_signal': _to_float_safe(latest_row.get('signal'), default=0.0),
            'close': current_price,
            'atr': current_atr,
            'adx': _to_float_safe(latest_row.get('adx'), default=0.0),
            'volume': base_volume,
            'quote_volume': quote_volume,
            'price_position_score': _to_float_safe(latest_row.get('price_position_score'), default=1.5),
            'bb_upper': _to_float_safe(latest_row.get('bb_upper'), default=0.0),
            'bb_lower': _to_float_safe(latest_row.get('bb_lower'), default=0.0),
            'market_trend': trend_data  # Add trend data for downtrend protection
        }
        run_id = str(tier_run_id or f"{pair}-{int(time.time())}")
        score_result = None
        try:
            score_result = signal_scorer.score(
                tech_data=tech_data,
                ai_data=ai_data,
                candidate_meta={
                    "quote_volume": quote_volume,
                    "source": "trading_cycle",
                },
            )
            print(
                f"   - Signal Score: {score_result.total_score:.1f}/100 "
                f"(threshold: {score_result.threshold:.1f})"
            )
            telemetry_tracker.track_feature_snapshot(
                run_id=run_id,
                symbol=pair,
                timeframe=timeframe,
                features=tech_data,
                ai_confidence=_to_float_safe(ai_data.get('confidence'), default=0.0),
                sentiment_score=_to_float_safe(ai_data.get('sentiment_score'), default=0.0),
            )
            telemetry_tracker.track_signal_score(
                run_id=run_id,
                symbol=pair,
                timeframe=timeframe,
                total_score=score_result.total_score,
                threshold=score_result.threshold,
                passed_threshold=score_result.passed_threshold,
                component_scores=score_result.component_scores,
                weighted_scores=score_result.weighted_scores,
                weights=score_result.weights,
                notes=score_result.notes,
            )
        except Exception as scoring_error:
            print(f"Signal scoring save error for {pair}: {scoring_error}")
        
        is_sim = (mode == "PAPER")
        ai_rec = analysis.get('recommendation', 'UNKNOWN')

        # Skip non-actionable signals entirely (no DB write, no execution)
        if ai_rec in ['WAIT', 'HOLD']:
            print(f"   - AI Recommendation: {ai_rec} -- Skipping (non-actionable)")
            return
            
        # SAFETY: Double Check Intent vs Recommendation
        if intent == "ENTRY" and ai_rec == "SELL":
            print("   - ⚠️ SAFETY: AI recommended SELL during ENTRY scan. Ignoring.")
            return
        if intent == "EXIT" and ai_rec == "BUY":
            print("   - ⚠️ SAFETY: AI recommended BUY during EXIT scan. Ignoring.")
            return

        verdict = judge.evaluate(ai_data, tech_data, balance, is_sim=is_sim, asset_id=asset_id)
        if (
            ai_rec == "BUY"
            and score_result
            and score_result.score_gate_enabled
            and not score_result.passed_threshold
        ):
            verdict = TradeDecision(
                decision="REJECTED",
                size=0,
                reason=f"Signal Score Gate: {score_result.total_score:.1f} < {score_result.threshold:.1f}",
            )

        print(f"   - AI Recommendation: {ai_rec} (Confidence: {ai_data['confidence']}%)")
        print(f"   - Judge Verdict: {verdict.decision} -> {verdict.reason}")

        # P4: store rule evaluation snapshot for replay/debug
        try:
            min_conf = float(judge.config.get("AI_CONF_THRESHOLD", 60))
            rsi_limit = float(judge.config.get("RSI_THRESHOLD", 75))
            telemetry_tracker.track_rule_evaluation(
                run_id=run_id,
                symbol=pair,
                rule_name="AI_CONF_THRESHOLD",
                passed=float(ai_data.get("confidence", 0)) >= min_conf,
                observed_value=ai_data.get("confidence"),
                threshold_value=min_conf,
                reason=verdict.reason,
            )
            telemetry_tracker.track_rule_evaluation(
                run_id=run_id,
                symbol=pair,
                rule_name="RSI_THRESHOLD",
                passed=float(tech_data.get("rsi", 0)) <= rsi_limit,
                observed_value=tech_data.get("rsi"),
                threshold_value=rsi_limit,
                reason=verdict.reason,
            )
            if score_result:
                telemetry_tracker.track_rule_evaluation(
                    run_id=run_id,
                    symbol=pair,
                    rule_name="SIGNAL_SCORE_THRESHOLD",
                    passed=score_result.passed_threshold,
                    observed_value=score_result.total_score,
                    threshold_value=score_result.threshold,
                    reason=verdict.reason,
                )
            telemetry_tracker.track_rule_evaluation(
                run_id=run_id,
                symbol=pair,
                rule_name="JUDGE_FINAL",
                passed=verdict.decision == "APPROVED",
                observed_value=verdict.decision,
                threshold_value="APPROVED",
                reason=verdict.reason,
            )
        except Exception as telemetry_error:
            print(f"Telemetry rule save error: {telemetry_error}")

        # Log Signal to DB (only BUY/SELL, not WAIT/HOLD)
        signal_data = {
            "asset_id": asset_id,
            "signal_type": ai_rec,
            "entry_target": current_price,
            "entry_atr": current_atr,
            "status": "PENDING" if verdict.decision == "APPROVED" else "REJECTED",
            "judge_reason": verdict.reason,
            "is_sim": is_sim
        }
        
        # For SELL signals, attach default exit reason if Approved
        # (This is handled in executor by default, but we can be explicit here if we want)
        if ai_rec == "SELL":
             # Extract reasoning (limit length to fit DB text field comfortably)
             reasoning_text = str(analysis.get('reasoning', '')).replace("'", "").replace('"', '')[:100]
             signal_data['exit_reason'] = f"AI_SELL_SIGNAL: {reasoning_text}"
             
        signal_entry = db.table("trade_signals").insert(signal_data).execute()
        
        # 4. SNIPER (Executor)
        if verdict.decision == "APPROVED":
            print("4. Sniper Firing!")
            log_activity("Sniper", f"🔫 Executing {pair}...", "WARNING")
            # Use full signal object
            full_signal = signal_entry.data[0]
            full_signal['assets'] = {'symbol': pair} # Manual hydrate for simplicity
            full_signal['order_size'] = verdict.size  # USDT amount from Judge
            
            # Pass exit reason explicitly to executor if SELL
            if ai_rec == "SELL":
                # Ensure the detailed reason is passed
                full_signal['exit_reason'] = signal_data['exit_reason']

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


def set_bot_status(status, detail=None):
    """Persist high-level runtime status for dashboard/API summary."""
    normalized = str(status or "").strip().upper()
    allowed = {"STARTING", "ACTIVE", "PAUSED", "STOPPED", "DEGRADED", "ERROR", "IDLE"}
    if normalized not in allowed:
        normalized = "ACTIVE"
    try:
        db.table("bot_config").upsert({"key": "BOT_STATUS", "value": normalized}).execute()
        if detail:
            db.table("bot_config").upsert({"key": "BOT_STATUS_DETAIL", "value": str(detail)}).execute()
    except Exception as e:
        print(f"BOT_STATUS update error: {e}")

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
                    "exit_reason": "TRAILING_STOP",  # NEW: Track why we sold
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


def sync_post_trade_attribution(limit=30):
    """
    P4 backfill: ensure every recently closed position has attribution row.
    """
    try:
        closed = (
            db.table("positions")
            .select("id,pnl,exit_reason,closed_at")
            .eq("is_open", False)
            .order("closed_at", desc=True)
            .limit(limit)
            .execute()
        )
        if not closed.data:
            return

        for row in closed.data:
            position_id = row.get("id")
            if not position_id:
                continue

            already = (
                db.table("post_trade_attribution")
                .select("id")
                .eq("position_id", position_id)
                .limit(1)
                .execute()
            )
            if already.data:
                continue

            pnl = float(row.get("pnl") or 0.0)
            outcome = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAK_EVEN"
            telemetry_tracker.track_post_trade_attribution(
                position_id=position_id,
                run_id=None,
                outcome=outcome,
                pnl=pnl,
                exit_reason=row.get("exit_reason"),
                ai_vs_rule_alignment="UNKNOWN",
                notes="Auto-generated from closed position",
            )
    except Exception as e:
        print(f"Post-trade attribution sync error: {e}")

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
    
    radar_limit = int(float(get_config_value("RADAR_SCAN_LIMIT", 100) or 100))
    radar_limit = max(20, min(radar_limit, 200))
    log_activity("Radar", f"Using radar scan limit={radar_limit}", "INFO")
    candidates_raw = radar.scan_market(limit=radar_limit, callback=update_status_db, logger=log_activity)

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

    # 2b. Persist candidate universe snapshot for Phase 1 replay/audit
    snapshot_id = f"farm-{farm_id}" if farm_id else f"farm-{int(time.time())}"
    try:
        persist_universe_snapshot(snapshot_id=snapshot_id, candidates=candidates, stage="farming_cycle")
    except Exception as snapshot_error:
        print(f"Universe snapshot error: {snapshot_error}")
        
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

    runtime_status = get_bot_runtime_status()
    if runtime_status == "STOPPED":
        set_bot_status("STOPPED", "⛔ Bot stopped by operator")
        log_activity("System", "⛔ Bot is STOPPED. Skipping trading cycle.", "WARNING")
        return
    if runtime_status == "PAUSED":
        set_bot_status("PAUSED", "⏸️ Bot paused by operator")
        log_activity("System", "⏸️ Bot is PAUSED. Skipping trading cycle.", "WARNING")
        return
    set_bot_status("ACTIVE")

    # 0. Check trailing stops BEFORE processing new signals
    check_trailing_stops()
    # 0a. Sync P4 attribution rows for recently closed positions
    sync_post_trade_attribution(limit=30)

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
        
        # Determine Mode/Sim Status for filtering
        try:
            mode_cfg = db.table("bot_config").select("value").eq("key", "TRADING_MODE").execute()
            current_mode = str(mode_cfg.data[0]['value']).replace('"', '').strip() if mode_cfg.data else "PAPER"
            is_sim_mode = (current_mode == "PAPER")
        except:
            current_mode = "PAPER"
            is_sim_mode = True

        # === PHASE A: HUNTING (BUY Opportunities) ===
        # Scan Active Candidates -> Check for ENTRY only
        
        # Filter out held positions from candidates to avoid redundant BUY checks (unless DCA logic added later)
        open_positions = []
        try:
            open_pos_res = db.table("positions").select("asset_id, assets(symbol)")\
                .eq("is_open", True)\
                .eq("is_sim", is_sim_mode)\
                .execute()
            open_positions = open_pos_res.data if open_pos_res.data else []
        except Exception as e:
            print(f"Error fetching open positions: {e}")

        held_symbols = set()
        for pos in open_positions:
            sym = pos.get('assets', {}).get('symbol') if pos.get('assets') else None
            if sym: held_symbols.add(sym)

        buy_candidates = [c for c in candidates if c not in held_symbols]
        
        update_status_db(f"🔫 Sniper Phase A: Hunting BUYs in {len(buy_candidates)} pairs (Next Farm: {next_farm_in}h)")
        
        for i, symbol in enumerate(buy_candidates):
            set_heartbeat()
            # Loop 1: ENTRY ONLY
            process_pair(symbol, timeframe, intent="ENTRY")
            time.sleep(1)

        # === PHASE B: MANAGING (SELL Opportunities) ===
        # Scan Open Positions -> Check for EXIT only
        
        if held_symbols:
            update_status_db(f"🔫 Sniper Phase B: Managing exits for {len(held_symbols)} positions")
            for symbol in held_symbols:
                set_heartbeat()
                # Loop 2: EXIT ONLY
                process_pair(symbol, timeframe, intent="EXIT")
                time.sleep(1)
        else:
             print("ℹ️ No open positions to manage.")
            
    except Exception as e:
        set_bot_status("DEGRADED", f"Trading cycle error: {e}")
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
        set_bot_status("STARTING", "🚀 Booting Zenith bot services")
        log_activity("System", "🚀 Zenith Bot Started (6-Role Architecture)", "SUCCESS")

        # Start Watchdog
        wd = threading.Thread(target=start_watchdog, daemon=True)
        wd.start()

        # Init heartbeat
        set_heartbeat()
        
        # --- IMMEDIATE FEEDBACK FOR USER ---
        # Write "I am Alive" signal to DB immediately so Dashboard turns GREEN
        try:
             current_time_str = str(time.time())
             db.table("bot_config").upsert({"key": "LAST_HEARTBEAT", "value": current_time_str}).execute()

             # Record Start Time (for Uptime tracking) - only if not already set
             start_time_check = db.table("bot_config").select("value").eq("key", "BOT_START_TIME").execute()
             if not start_time_check.data:
                 db.table("bot_config").upsert({"key": "BOT_START_TIME", "value": current_time_str}).execute()
                 print("💓 Heartbeat Initialized | 🕐 Start Time Set (First Run)")
             else:
                 print("💓 Heartbeat Initialized | 🕐 Start Time Preserved")
             
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

        # 2. Initialize Trading Sessions (Create if missing after factory reset)
        print("📊 Initializing Trading Sessions...")
        try:
            from src.session_manager import get_active_session, create_session

            # Check/create session for PAPER mode
            paper_session = get_active_session(mode='PAPER')
            if not paper_session:
                # Get current simulation balance
                sim_wallet = db.table("simulation_portfolio").select("balance").eq("id", 1).execute()
                start_balance = float(sim_wallet.data[0]['balance']) if sim_wallet.data else 1000.0
                paper_id = create_session(mode='PAPER', start_balance=start_balance)
                if paper_id:
                    print("✅ Created PAPER session (auto-start after reset)")
                    log_activity("System", "Auto-created PAPER trading session", "INFO")
            else:
                print(f"✅ Resuming PAPER session: {paper_session['session_name']}")

            # Check/create session for LIVE mode
            live_session = get_active_session(mode='LIVE')
            if not live_session:
                # Get current live balance (or default)
                try:
                    bal_data = price_spy.get_account_balance()
                    start_balance = bal_data['total'].get('USDT', 1000.0) if bal_data else 1000.0
                except:
                    start_balance = 1000.0
                live_id = create_session(mode='LIVE', start_balance=start_balance)
                if live_id:
                    print("✅ Created LIVE session (auto-start after reset)")
                    log_activity("System", "Auto-created LIVE trading session", "INFO")
            else:
                print(f"✅ Resuming LIVE session: {live_session['session_name']}")
        except Exception as e:
            print(f"⚠️ Session initialization error: {e}")
            log_activity("System", f"Session initialization failed: {e}", "ERROR")

        # 2. Run Trading Cycle (Can take time)
        print("🚀 Starting First Trading Cycle...")
        try:
            set_bot_status("ACTIVE", "✅ First trading cycle starting")
            run_trading_cycle()
        except Exception as e:
             # Log but DO NOT CRASH. The scheduler will try again later.
             set_bot_status("DEGRADED", f"Initial trading cycle failed: {e}")
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
                set_bot_status("DEGRADED", f"Loop error: {e}")
                log_activity("System", f"Loop Error: {e}", "ERROR")
                time.sleep(5)
    except Exception as e:
        # Emergency Log
        set_bot_status("ERROR", f"Critical crash: {e}")
        try:
             db.table("system_logs").insert({"role": "System", "message": f"CRITICAL CRASH: {e}", "level": "ERROR"}).execute()
        except Exception:
            print(f"Fatal: {e}")

if __name__ == "__main__":
    start()
