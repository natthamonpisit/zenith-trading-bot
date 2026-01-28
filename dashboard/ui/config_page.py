import streamlit as st
import time
from .utils import get_cfg

def render_config_page(db):
    st.markdown("### ⚙️ Strategy Configuration")
    st.caption("Adjust the brain parameters of the AI Strategist and Risk Judge.")

    # Paper Trading Session Management
    with st.container(border=True):
        st.markdown("#### 🔄 Paper Trading Session")

        try:
            # Import session manager functions
            import sys
            import os
            sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
            from src.session_manager import get_active_session, reset_simulation_session, get_session_count

            # Show current session info
            current_session = get_active_session(mode='PAPER')
            if current_session:
                st.info(f"**Current Session:** {current_session['session_name']}")
                started = current_session['started_at'][:19] if current_session['started_at'] else "N/A"
                balance = float(current_session['current_balance'])
                net_pnl = float(current_session['net_pnl'])

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Started", started)
                c2.metric("Balance", f"${balance:,.2f}")
                c3.metric("Net P&L", f"${net_pnl:,.2f}")
                c4.metric("Trades", current_session['total_trades'])

            # Reset section
            with st.expander("🆕 Start New Simulation", expanded=False):
                st.warning("⚠️ This will end the current session and start a fresh simulation.")

                r1, r2 = st.columns(2)
                with r1:
                    new_balance = st.number_input(
                        "Starting Balance ($)",
                        min_value=100.0,
                        max_value=1000000.0,
                        value=1000.0,
                        step=100.0,
                        help="Initial capital for the new simulation session"
                    )
                with r2:
                    session_count = get_session_count(mode='PAPER')
                    default_name = f"Paper Run #{session_count + 1}"
                    session_name = st.text_input(
                        "Session Name (optional)",
                        value=default_name,
                        help="Custom name for this simulation run"
                    )

                if st.button("🔄 Reset & Start Fresh", type="secondary", use_container_width=True):
                    try:
                        new_session_id = reset_simulation_session(
                            new_balance=new_balance,
                            session_name=session_name
                        )
                        if new_session_id:
                            st.success(f"✅ Started new session: {session_name}")
                            st.info("💡 Previous session data has been archived and can be viewed in Session History.")
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("❌ Failed to create new session")
                    except Exception as e:
                        st.error(f"Reset failed: {e}")

        except Exception as e:
            st.error(f"Session management error: {e}")

    st.markdown("---")

    with st.container(border=True):
        st.markdown("#### 🧠 AI & Logic Parameters")
        col1, col2 = st.columns(2)
        
        with col1:
            try:
                current_ai = int(float(str(get_cfg(db, "AI_CONF_THRESHOLD", 60))))
            except:
                current_ai = 60
            new_ai = st.slider("Min AI Confidence (%)", 0, 100, current_ai, help="Signals below this will be REJECTED.")
            
            try:
                current_rsi = int(float(str(get_cfg(db, "RSI_THRESHOLD", 75))))
            except:
                current_rsi = 75
            new_rsi = st.slider("RSI Veto Threshold", 50, 90, current_rsi, help="Never BUY if RSI is above this level.")

        with col2:
            try:
                current_pos_size = float(str(get_cfg(db, "POSITION_SIZE_PCT", 5.0)))
            except:
                current_pos_size = 5.0
            new_pos_size = st.number_input("Position Size (% of Wallet)", 1.0, 100.0, current_pos_size, step=0.5)
            
            try:
                current_risk = float(str(get_cfg(db, "MAX_RISK_PER_TRADE", 2.0)))
            except:
                current_risk = 2.0
            new_risk = st.number_input("Max Risk Per Trade (%)", 0.1, 10.0, current_risk, step=0.1)

        st.markdown("#### ⚖️ Flow Controls")
        c1, c2, c3 = st.columns(3)
        with c1:
            try:
                current_max_pos = int(float(str(get_cfg(db, "MAX_OPEN_POSITIONS", 5))))
            except:
                current_max_pos = 5
            new_max_pos = st.number_input("Max Open Positions", 1, 20, current_max_pos)
        with c2:
            curr_mode = str(get_cfg(db, "TRADING_MODE", "PAPER")).replace('"', '')
            new_mode = st.radio("Select Mode", ["PAPER", "LIVE"], index=0 if curr_mode=="PAPER" else 1, horizontal=True)
        with c3:
            curr_tf = str(get_cfg(db, "TIMEFRAME", "1h")).replace('"', '')
            new_tf = st.selectbox("Trading Timeframe", ["5m", "15m", "30m", "1h", "4h", "1d"], index=["5m", "15m", "30m", "1h", "4h", "1d"].index(curr_tf) if curr_tf in ["5m", "15m", "30m", "1h", "4h", "1d"] else 3)

        st.markdown("#### 📜 Judge Checkbox Protocols")
        cb1, cb2 = st.columns(2)
        with cb1:
            # Trend Check (EMA)
            trend_val = str(get_cfg(db, "ENABLE_EMA_TREND", "false")).replace('"', '').lower() == 'true'
            new_trend = st.checkbox("✅ Trend Veto (Price > EMA50)", value=trend_val, help="Reject BUY if price is below EMA 50 (Downtrend).")
        with cb2:
            # Momentum Check (MACD)
            macd_val = str(get_cfg(db, "ENABLE_MACD_MOMENTUM", "false")).replace('"', '').lower() == 'true'
            new_macd = st.checkbox("✅ Momentum Veto (Bullish MACD)", value=macd_val, help="Reject BUY if MACD < Signal Line.")

        st.markdown("#### 📉 Trailing Stop Settings")
        ts1, ts2, ts3 = st.columns(3)
        with ts1:
            trail_enabled = str(get_cfg(db, "TRAILING_STOP_ENABLED", "true")).replace('"', '').lower() == 'true'
            new_trail_enabled = st.checkbox("Enable Trailing Stop", value=trail_enabled, help="Auto-sell when price drops X% from peak.")
        with ts2:
            try:
                trail_pct = float(str(get_cfg(db, "TRAILING_STOP_PCT", 3.0)))
            except:
                trail_pct = 3.0
            new_trail_pct = st.number_input("Trail Distance (%)", 0.5, 20.0, trail_pct, step=0.5, help="Sell if price drops this % from highest point.")
        with ts3:
            try:
                min_prof = float(str(get_cfg(db, "MIN_PROFIT_TO_TRAIL_PCT", 1.0)))
            except:
                min_prof = 1.0
            new_min_prof = st.number_input("Min Profit to Activate (%)", 0.0, 50.0, min_prof, step=0.5, help="Trailing stop only activates after this profit %.")

        # ATR-based trailing stop settings
        st.markdown("##### ATR-Based Mode")
        atr1, atr2 = st.columns(2)
        with atr1:
            use_atr = str(get_cfg(db, "TRAILING_STOP_USE_ATR", "false")).replace('"', '').lower() == 'true'
            new_use_atr = st.checkbox("Use ATR-Based Trailing Stop", value=use_atr, help="Use ATR (volatility) instead of fixed % for trailing stop distance. More adaptive to market conditions.")
        with atr2:
            try:
                atr_mult = float(str(get_cfg(db, "TRAILING_STOP_ATR_MULTIPLIER", 2.0)))
            except:
                atr_mult = 2.0
            new_atr_mult = st.number_input("ATR Multiplier", 1.0, 5.0, atr_mult, step=0.5, help="Trail distance = ATR × Multiplier. Higher = wider stop, lower = tighter stop.", disabled=not new_use_atr)

        # --- 3. Head Hunter (Fundamental) Config ---
        st.subheader("🕵️ Head Hunter Settings")
        
        # A. Trading Universe
        current_universe = str(get_cfg(db, "TRADING_UNIVERSE", "ALL")).replace('"', '')
        new_universe = st.selectbox(
            "Trading Universe Mode",
            ["ALL", "SAFE_LIST", "TOP_30"],
            index=["ALL", "SAFE_LIST", "TOP_30"].index(current_universe) if current_universe in ["ALL", "SAFE_LIST", "TOP_30"] else 0,
            help="SAFE_LIST: Only trade symbols in your Whitelist. ALL: Trade anything passing filters."
        )
        
        # B. Min Volume
        try:
            current_vol = float(str(get_cfg(db, "MIN_VOLUME", 10000000)))
        except:
            current_vol = 10000000.0
        new_vol = st.number_input(
            "Min 24h Volume (USDT)",
            min_value=0.0,
            value=current_vol,
            step=1000000.0,
            format="%f"
        )
        
        if st.button("Save Fundamental Config"):
            db.table("bot_config").upsert({"key": "TRADING_UNIVERSE", "value": new_universe}).execute()
            db.table("bot_config").upsert({"key": "MIN_VOLUME", "value": str(new_vol)}).execute()
            st.success("Saved!")
            st.rerun()

        st.markdown("---")

        # --- 4. Judge Config ---
        st.subheader("⚖️ Judge Protocols")
        if st.button("💾 Save Configuration", type="primary", use_container_width=True):
            try:
                configs = [
                    {"key": "AI_CONF_THRESHOLD", "value": str(new_ai)},
                    {"key": "RSI_THRESHOLD", "value": str(new_rsi)},
                    {"key": "POSITION_SIZE_PCT", "value": str(new_pos_size)},
                    {"key": "MAX_RISK_PER_TRADE", "value": str(new_risk)},
                    {"key": "MAX_OPEN_POSITIONS", "value": str(new_max_pos)},
                    {"key": "TRADING_MODE", "value": new_mode},
                    {"key": "TIMEFRAME", "value": new_tf},
                    {"key": "ENABLE_EMA_TREND", "value": str(new_trend).lower()},
                    {"key": "ENABLE_MACD_MOMENTUM", "value": str(new_macd).lower()},
                    {"key": "TRAILING_STOP_ENABLED", "value": str(new_trail_enabled).lower()},
                    {"key": "TRAILING_STOP_PCT", "value": str(new_trail_pct)},
                    {"key": "MIN_PROFIT_TO_TRAIL_PCT", "value": str(new_min_prof)},
                    {"key": "TRAILING_STOP_USE_ATR", "value": str(new_use_atr).lower()},
                    {"key": "TRAILING_STOP_ATR_MULTIPLIER", "value": str(new_atr_mult)}
                ]
                for cfg in configs:
                    db.table("bot_config").upsert(cfg).execute()
                
                st.success("Configuration Updated! The Judge will now use these settings.")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Save Failed: {e}")

    # --- 5. Danger Zone ---
    st.markdown("---")
    st.subheader("🚨 Danger Zone")
    with st.container(border=True):
        st.markdown("""
        **Factory Reset:** This action will **permanently delete** all trading history, positions, logs, and signals.  
        Your **API Keys** and **Configuration** will be preserved.
        """)
        
        with st.expander("💣 Reveal Reset Controls"):
            delete_confirm = st.text_input("Type 'DELETE ALL DATA' to confirm:", key="delete_confirm_input")
            
            if st.button("🧨 Factory Reset All Data", type="primary"):
                if delete_confirm == "DELETE ALL DATA":
                    try:
                        with st.spinner("Deleting everything..."):
                            # Logic from scripts/reset_data.py
                            tables_to_truncate = [
                                "balance_snapshots", "config_change_log", "positions", "orders", 
                                "trade_signals", "ai_analysis", "market_snapshots", "performance_analytics", 
                                "system_logs", "trading_sessions"
                            ]
                            
                            # Clean Tables
                            for table in tables_to_truncate:
                                try:
                                    db.table(table).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
                                except: pass
                            
                            # Reset Sim Wallet
                            try:
                                db.table("simulation_portfolio").update({"balance": 1000.0, "total_pnl": 0}).eq("id", 1).execute()
                            except: pass

                            # Reset Start Time
                            try:
                                db.table("bot_config").upsert({"key": "BOT_START_TIME", "value": "0"}).execute()
                            except: pass
                        
                        st.success("✅ Factory Reset Complete! All history has been wiped.")
                        time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Reset Failed: {e}")
                else:
                    st.error("❌ Confirmation text does not match.")
