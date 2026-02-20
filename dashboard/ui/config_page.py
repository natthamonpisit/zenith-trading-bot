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

        st.markdown("#### 🛡️ Downtrend Protection")
        st.caption("Protect capital during unfavorable market conditions")

        dp1, dp2, dp3 = st.columns(3)

        with dp1:
            downtrend_enabled = str(get_cfg(db, "ENABLE_DOWNTREND_PROTECTION", "false")).replace('"', '').lower() == 'true'
            new_downtrend_enabled = st.checkbox(
                "Enable Downtrend Protection",
                value=downtrend_enabled,
                help="Activate market-wide trend analysis to adjust trading behavior"
            )

        with dp2:
            current_mode = str(get_cfg(db, "DOWNTREND_PROTECTION_MODE", "MODERATE")).replace('"', '')
            new_protection_mode = st.selectbox(
                "Protection Mode",
                ["STRICT", "MODERATE", "SELECTIVE"],
                index=["STRICT", "MODERATE", "SELECTIVE"].index(current_mode) if current_mode in ["STRICT", "MODERATE", "SELECTIVE"] else 1,
                help="STRICT: Block all BUYs in downtrends | MODERATE: Higher AI threshold + smaller positions | SELECTIVE: Only buy strong coins",
                disabled=not new_downtrend_enabled
            )

        with dp3:
            try:
                current_boost = float(str(get_cfg(db, "DOWNTREND_AI_BOOST", 20)))
            except:
                current_boost = 20.0
            new_ai_boost = st.number_input(
                "Downtrend AI Boost (%)",
                min_value=0.0,
                max_value=50.0,
                value=current_boost,
                step=5.0,
                help="Additional AI confidence required during downtrends (MODERATE mode)",
                disabled=not new_downtrend_enabled
            )

        with st.expander("🔧 Advanced Downtrend Settings", expanded=False):
            adv1, adv2 = st.columns(2)

            with adv1:
                try:
                    size_reduction = float(str(get_cfg(db, "DOWNTREND_SIZE_REDUCTION_PCT", 30)))
                except:
                    size_reduction = 30.0
                new_size_reduction = st.number_input(
                    "Position Size Reduction (%)",
                    min_value=0.0,
                    max_value=70.0,
                    value=size_reduction,
                    step=5.0,
                    help="Reduce position size by this % during moderate downtrends",
                    disabled=not new_downtrend_enabled
                )

            with adv2:
                try:
                    adx_threshold = float(str(get_cfg(db, "ADX_TREND_THRESHOLD", 25)))
                except:
                    adx_threshold = 25.0
                new_adx_threshold = st.number_input(
                    "ADX Trend Threshold",
                    min_value=15.0,
                    max_value=40.0,
                    value=adx_threshold,
                    step=5.0,
                    help="ADX above this = trending market (default: 25)",
                    disabled=not new_downtrend_enabled
                )

        if new_downtrend_enabled:
            st.info(f"""
            **Mode: {new_protection_mode}** | Hybrid Detection: EMA Alignment + ADX ({new_adx_threshold}) + Price Position

            {
                "All BUYs blocked in downtrends" if new_protection_mode == "STRICT" else
                f"Strong downtrends blocked. Moderate: +{new_ai_boost}% AI conf, {new_size_reduction}% smaller positions" if new_protection_mode == "MODERATE" else
                "Only coins with relative strength (above EMA200) allowed in downtrends"
            }
            """)

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

        st.markdown("#### 🎯 Phase 2: Order Plan & TP Ladder")
        st.caption("Deterministic plan before execution: Initial SL, TP1 partial, TP2 full exit, and breakeven promotion.")

        op1, op2, op3 = st.columns(3)
        with op1:
            order_plan_enabled = str(get_cfg(db, "ORDER_PLAN_ENABLED", "true")).replace('"', '').lower() == 'true'
            new_order_plan_enabled = st.checkbox(
                "Enable Order Plan",
                value=order_plan_enabled,
                help="Build and persist deterministic order plan before BUY execution."
            )
        with op2:
            tp_ladder_enabled = str(get_cfg(db, "ENABLE_TP_LADDER", "true")).replace('"', '').lower() == 'true'
            new_tp_ladder_enabled = st.checkbox(
                "Enable TP Ladder",
                value=tp_ladder_enabled,
                help="Activate TP1 partial + TP2 full exit monitor for open positions."
            )
        with op3:
            current_plan_trailing_mode = str(get_cfg(db, "ORDER_PLAN_TRAILING_MODE", "ATR")).replace('"', '').upper()
            if current_plan_trailing_mode not in ["ATR", "PERCENT", "NONE"]:
                current_plan_trailing_mode = "ATR"
            new_plan_trailing_mode = st.selectbox(
                "Plan Trailing Mode",
                ["ATR", "PERCENT", "NONE"],
                index=["ATR", "PERCENT", "NONE"].index(current_plan_trailing_mode),
                help="Preferred trailing mode for planned positions."
            )

        op_adv1, op_adv2, op_adv3 = st.columns(3)
        with op_adv1:
            try:
                sl_atr_mult = float(str(get_cfg(db, "STOP_LOSS_ATR_MULTIPLIER", 1.8)))
            except:
                sl_atr_mult = 1.8
            new_sl_atr_mult = st.number_input(
                "Initial SL ATR Multiplier",
                min_value=0.5,
                max_value=10.0,
                value=sl_atr_mult,
                step=0.1,
                help="Initial stop-loss distance = ATR × this multiplier."
            )
            try:
                min_sl_pct = float(str(get_cfg(db, "MIN_STOP_LOSS_PCT", 0.8)))
            except:
                min_sl_pct = 0.8
            new_min_sl_pct = st.number_input(
                "Min Stop Loss (%)",
                min_value=0.1,
                max_value=10.0,
                value=min_sl_pct,
                step=0.1,
                help="Minimum stop-loss distance from entry price."
            )
        with op_adv2:
            try:
                tp1_r = float(str(get_cfg(db, "TP1_R_MULTIPLE", 1.0)))
            except:
                tp1_r = 1.0
            new_tp1_r = st.number_input(
                "TP1 R Multiple",
                min_value=0.5,
                max_value=5.0,
                value=tp1_r,
                step=0.1,
                help="TP1 distance in R units (risk units)."
            )
            try:
                tp2_r = float(str(get_cfg(db, "TP2_R_MULTIPLE", 2.0)))
            except:
                tp2_r = 2.0
            new_tp2_r = st.number_input(
                "TP2 R Multiple",
                min_value=1.0,
                max_value=10.0,
                value=tp2_r,
                step=0.1,
                help="TP2 full-exit distance in R units."
            )
        with op_adv3:
            try:
                tp1_partial = float(str(get_cfg(db, "TP1_PARTIAL_PCT", 50.0)))
            except:
                tp1_partial = 50.0
            new_tp1_partial = st.number_input(
                "TP1 Partial Close (%)",
                min_value=5.0,
                max_value=95.0,
                value=tp1_partial,
                step=5.0,
                help="Position percentage to close when TP1 is hit."
            )
            try:
                breakeven_buffer = float(str(get_cfg(db, "BREAKEVEN_BUFFER_PCT", 0.1)))
            except:
                breakeven_buffer = 0.1
            new_breakeven_buffer = st.number_input(
                "Breakeven Buffer (%)",
                min_value=0.0,
                max_value=1.0,
                value=breakeven_buffer,
                step=0.05,
                help="After TP1, move stop to entry plus this buffer."
            )

        st.info(
            f"Order Plan {'ON' if new_order_plan_enabled else 'OFF'} | "
            f"TP Ladder {'ON' if new_tp_ladder_enabled else 'OFF'} | "
            f"Trailing Mode: {new_plan_trailing_mode}"
        )

        # --- 3. Head Hunter (Fundamental) Config ---
        st.subheader("🕵️ Head Hunter Settings")
        
        # A. Trading Universe
        current_universe = str(get_cfg(db, "TRADING_UNIVERSE", "TOP_100")).replace('"', '')
        new_universe = st.selectbox(
            "Trading Universe Mode",
            ["TOP_100", "ALL", "SAFE_LIST", "TOP_30"],
            index=["TOP_100", "ALL", "SAFE_LIST", "TOP_30"].index(current_universe) if current_universe in ["TOP_100", "ALL", "SAFE_LIST", "TOP_30"] else 0,
            help="TOP_100: Keep top volume 100 assets. SAFE_LIST: Only whitelist. ALL: all assets passing filters."
        )

        current_whitelist_policy = str(get_cfg(db, "WHITELIST_POLICY", "RELAXED")).replace('"', '')
        new_whitelist_policy = st.selectbox(
            "Whitelist Policy",
            ["RELAXED", "IGNORE", "STRICT"],
            index=["RELAXED", "IGNORE", "STRICT"].index(current_whitelist_policy) if current_whitelist_policy in ["RELAXED", "IGNORE", "STRICT"] else 0,
            help="RELAXED: whitelist gets lower volume threshold. IGNORE: no whitelist gate. STRICT: whitelist only.",
        )
        
        # B. Min Volume
        try:
            current_vol = float(str(get_cfg(db, "MIN_VOLUME", 10000)))
        except:
            current_vol = 10000.0
        new_vol = st.number_input(
            "Min 24h Volume (USDT)",
            min_value=0.0,
            value=current_vol,
            step=1000.0,
            format="%f"
        )

        try:
            current_radar_limit = int(float(str(get_cfg(db, "RADAR_SCAN_LIMIT", 100))))
        except:
            current_radar_limit = 100
        new_radar_limit = st.number_input(
            "Radar Scan Limit",
            min_value=20,
            max_value=300,
            value=current_radar_limit,
            step=5,
            help="Max symbols requested from Radar in each farming/manual scan."
        )
        
        if st.button("Save Fundamental Config"):
            db.table("bot_config").upsert({"key": "TRADING_UNIVERSE", "value": new_universe}).execute()
            db.table("bot_config").upsert({"key": "WHITELIST_POLICY", "value": new_whitelist_policy}).execute()
            db.table("bot_config").upsert({"key": "MIN_VOLUME", "value": str(new_vol)}).execute()
            db.table("bot_config").upsert({"key": "RADAR_SCAN_LIMIT", "value": str(new_radar_limit)}).execute()
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
                    {"key": "ENABLE_DOWNTREND_PROTECTION", "value": str(new_downtrend_enabled).lower()},
                    {"key": "DOWNTREND_PROTECTION_MODE", "value": new_protection_mode},
                    {"key": "DOWNTREND_AI_BOOST", "value": str(new_ai_boost)},
                    {"key": "DOWNTREND_SIZE_REDUCTION_PCT", "value": str(new_size_reduction)},
                    {"key": "ADX_TREND_THRESHOLD", "value": str(new_adx_threshold)},
                    {"key": "TRAILING_STOP_ENABLED", "value": str(new_trail_enabled).lower()},
                    {"key": "TRAILING_STOP_PCT", "value": str(new_trail_pct)},
                    {"key": "MIN_PROFIT_TO_TRAIL_PCT", "value": str(new_min_prof)},
                    {"key": "TRAILING_STOP_USE_ATR", "value": str(new_use_atr).lower()},
                    {"key": "TRAILING_STOP_ATR_MULTIPLIER", "value": str(new_atr_mult)},
                    {"key": "ORDER_PLAN_ENABLED", "value": str(new_order_plan_enabled).lower()},
                    {"key": "ENABLE_TP_LADDER", "value": str(new_tp_ladder_enabled).lower()},
                    {"key": "ORDER_PLAN_TRAILING_MODE", "value": new_plan_trailing_mode},
                    {"key": "STOP_LOSS_ATR_MULTIPLIER", "value": str(new_sl_atr_mult)},
                    {"key": "MIN_STOP_LOSS_PCT", "value": str(new_min_sl_pct)},
                    {"key": "TP1_R_MULTIPLE", "value": str(new_tp1_r)},
                    {"key": "TP2_R_MULTIPLE", "value": str(new_tp2_r)},
                    {"key": "TP1_PARTIAL_PCT", "value": str(new_tp1_partial)},
                    {"key": "BREAKEVEN_BUFFER_PCT", "value": str(new_breakeven_buffer)}
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

                            # Reset Start Time (Set to NOW so uptime counts from reset)
                            try:
                                db.table("bot_config").upsert({"key": "BOT_START_TIME", "value": str(time.time())}).execute()
                            except: pass
                        
                        st.success("✅ Factory Reset Complete! All history has been wiped.")
                        time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Reset Failed: {e}")
                else:
                    st.error("❌ Confirmation text does not match.")
