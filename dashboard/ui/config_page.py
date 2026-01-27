import streamlit as st
import time
from .utils import get_cfg

def render_config_page(db):
    st.markdown("### ⚙️ Strategy Configuration")
    st.caption("Adjust the brain parameters of the AI Strategist and Risk Judge.")
    
    with st.container(border=True):
        st.markdown("#### 🧠 AI & Logic Parameters")
        col1, col2 = st.columns(2)
        
        with col1:
            current_ai = int(get_cfg(db, "AI_CONF_THRESHOLD", 60))
            new_ai = st.slider("Min AI Confidence (%)", 0, 100, current_ai, help="Signals below this will be REJECTED.")
            
            current_rsi = int(get_cfg(db, "RSI_THRESHOLD", 75))
            new_rsi = st.slider("RSI Veto Threshold", 50, 90, current_rsi, help="Never BUY if RSI is above this level.")

        with col2:
            current_pos_size = float(get_cfg(db, "POSITION_SIZE_PCT", 5.0))
            new_pos_size = st.number_input("Position Size (% of Wallet)", 1.0, 100.0, current_pos_size, step=0.5)
            
            current_risk = float(get_cfg(db, "MAX_RISK_PER_TRADE", 2.0))
            new_risk = st.number_input("Max Risk Per Trade (%)", 0.1, 10.0, current_risk, step=0.1)

        st.markdown("#### ⚖️ Flow Controls")
        c1, c2, c3 = st.columns(3)
        with c1:
            current_max_pos = int(get_cfg(db, "MAX_OPEN_POSITIONS", 5))
            new_max_pos = st.number_input("Max Open Positions", 1, 20, current_max_pos)
        with c2:
            curr_mode = get_cfg(db, "TRADING_MODE", "PAPER").replace('"', '')
            new_mode = st.radio("Select Mode", ["PAPER", "LIVE"], index=0 if curr_mode=="PAPER" else 1, horizontal=True)
        with c3:
            curr_tf = get_cfg(db, "TIMEFRAME", "1h").replace('"', '')
            new_tf = st.selectbox("Trading Timeframe", ["5m", "15m", "30m", "1h", "4h", "1d"], index=["5m", "15m", "30m", "1h", "4h", "1d"].index(curr_tf) if curr_tf in ["5m", "15m", "30m", "1h", "4h", "1d"] else 3)

        st.markdown("#### 📜 Judge Checkbox Protocols")
        cb1, cb2 = st.columns(2)
        with cb1:
            # Trend Check (EMA)
            trend_val = get_cfg(db, "ENABLE_EMA_TREND", "false").replace('"', '').lower() == 'true'
            new_trend = st.checkbox("✅ Trend Veto (Price > EMA50)", value=trend_val, help="Reject BUY if price is below EMA 50 (Downtrend).")
        with cb2:
            # Momentum Check (MACD)
            macd_val = get_cfg(db, "ENABLE_MACD_MOMENTUM", "false").replace('"', '').lower() == 'true'
            new_macd = st.checkbox("✅ Momentum Veto (Bullish MACD)", value=macd_val, help="Reject BUY if MACD < Signal Line.")

        st.markdown("#### 📉 Trailing Stop Settings")
        ts1, ts2, ts3 = st.columns(3)
        with ts1:
            trail_enabled = get_cfg(db, "TRAILING_STOP_ENABLED", "true").replace('"', '').lower() == 'true'
            new_trail_enabled = st.checkbox("Enable Trailing Stop", value=trail_enabled, help="Auto-sell when price drops X% from peak.")
        with ts2:
            trail_pct = float(get_cfg(db, "TRAILING_STOP_PCT", 3.0))
            new_trail_pct = st.number_input("Trail Distance (%)", 0.5, 20.0, trail_pct, step=0.5, help="Sell if price drops this % from highest point.")
        with ts3:
            min_prof = float(get_cfg(db, "MIN_PROFIT_TO_TRAIL_PCT", 1.0))
            new_min_prof = st.number_input("Min Profit to Activate (%)", 0.0, 50.0, min_prof, step=0.5, help="Trailing stop only activates after this profit %.")

        # --- 3. Head Hunter (Fundamental) Config ---
        st.subheader("🕵️ Head Hunter Settings")
        
        # A. Trading Universe
        current_universe = get_cfg(db, "TRADING_UNIVERSE", "ALL").replace('"', '')
        new_universe = st.selectbox(
            "Trading Universe Mode",
            ["ALL", "SAFE_LIST", "TOP_30"],
            index=["ALL", "SAFE_LIST", "TOP_30"].index(current_universe) if current_universe in ["ALL", "SAFE_LIST", "TOP_30"] else 0,
            help="SAFE_LIST: Only trade symbols in your Whitelist. ALL: Trade anything passing filters."
        )
        
        # B. Min Volume
        current_vol = float(get_cfg(db, "MIN_VOLUME", 10000000))
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
                    {"key": "MIN_PROFIT_TO_TRAIL_PCT", "value": str(new_min_prof)}
                ]
                for cfg in configs:
                    db.table("bot_config").upsert(cfg).execute()
                
                st.success("Configuration Updated! The Judge will now use these settings.")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Save Failed: {e}")
