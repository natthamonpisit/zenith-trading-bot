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
            current_ai = int(get_cfg(db, "AI_CONF_THRESHOLD", 75))
            new_ai = st.slider("Min AI Confidence (%)", 0, 100, current_ai, help="Signals below this will be REJECTED.")
            
            current_rsi = int(get_cfg(db, "RSI_THRESHOLD", 70))
            new_rsi = st.slider("RSI Veto Threshold", 50, 90, current_rsi, help="Never BUY if RSI is above this level.")

        with col2:
            current_pos_size = float(get_cfg(db, "POSITION_SIZE_PCT", 5.0))
            new_pos_size = st.number_input("Position Size (% of Wallet)", 1.0, 100.0, current_pos_size, step=0.5)
            
            current_risk = float(get_cfg(db, "MAX_RISK_PER_TRADE", 2.0))
            new_risk = st.number_input("Max Risk Per Trade (%)", 0.1, 10.0, current_risk, step=0.1)

        st.markdown("#### ⚖️ Flow Controls")
        c1, c2 = st.columns(2)
        with c1:
            current_max_pos = int(get_cfg(db, "MAX_OPEN_POSITIONS", 5))
            new_max_pos = st.number_input("Max Open Positions", 1, 20, current_max_pos)
        with c2:
            curr_mode = get_cfg(db, "TRADING_MODE", "PAPER").replace('"', '')
            new_mode = st.radio("Select Mode", ["PAPER", "LIVE"], index=0 if curr_mode=="PAPER" else 1, horizontal=True)

        st.markdown("---")
        if st.button("💾 Save Configuration", type="primary", use_container_width=True):
            try:
                configs = [
                    {"key": "AI_CONF_THRESHOLD", "value": str(new_ai)},
                    {"key": "RSI_THRESHOLD", "value": str(new_rsi)},
                    {"key": "POSITION_SIZE_PCT", "value": str(new_pos_size)},
                    {"key": "MAX_RISK_PER_TRADE", "value": str(new_risk)},
                    {"key": "MAX_OPEN_POSITIONS", "value": str(new_max_pos)},
                    {"key": "TRADING_MODE", "value": f'"{new_mode}"'}
                ]
                for cfg in configs:
                    db.table("bot_config").upsert(cfg).execute()
                
                st.success("Configuration Updated! The Judge will now use these settings.")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Save Failed: {e}")
