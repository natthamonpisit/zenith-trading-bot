import streamlit as st
import pandas as pd
import plotly.express as px
from src.database import get_db

# --- CONFIG ---
st.set_page_config(page_title="Zenith AI Bot", layout="wide", page_icon="🤖")
db = get_db()

st.title("🤖 Zenith AI-Quantamental Dashboard")

# --- SIDEBAR CONTROLS ---
st.sidebar.header("Control Center")
status = st.sidebar.radio("Bot Status", ["ACTIVE", "PAUSED", "STOPPED"], index=0)
if st.sidebar.button("🚨 EMERGENCY HALT"):
    # db.table("bot_config").upsert({"key": "BOT_STATUS", "value": "STOPPED"}).execute()
    st.sidebar.error("KILL SWITCH ACTIVATED. TRADING STOPPED.")

# --- 1. THE COCKPIT ---
st.subheader("📊 Portfolio Overview")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Equity", "$12,450.00", "+2.4%")
col2.metric("Open Positions", "3", "1 Long / 2 Short")
col3.metric("24h Volume", "$45,200")
col4.metric("AI Win Rate", "68%", "+5%")

# --- 2. ACTIVE POSITIONS ---
st.subheader("⚡ Active Positions (The Sniper)")
# Mock data for blueprint display if DB is empty
mock_positions = [
    {"symbol": "BTC/USDT", "side": "LONG", "entry": 64200, "current": 65100, "pnl": "+1.4%", "leverage": "5x"},
    {"symbol": "ETH/USDT", "side": "SHORT", "entry": 3200, "current": 3150, "pnl": "+1.5%", "leverage": "5x"},
]
st.dataframe(pd.DataFrame(mock_positions))

# --- 3. AUDIT LOGS ---
st.subheader("🕵️ AI Reasoning Audit (The Strategist)")
st.caption("Click on a trade to see why the AI & Judge approved it.")

mock_logs = [
    {
        "time": "10:45 AM",
        "symbol": "SOL/USDT",
        "signal": "BUY",
        "judge": "APPROVED",
        "ai_conf": 85,
        "reasoning": "RSI is resetting at 45 (Neutral). Volume spike detected (+200%). News sentiment is positive regarding ecosystem upgrades.",
        "judge_note": "Risk checks passed. Volatility is within bounds."
    },
    {
        "time": "09:30 AM",
        "symbol": "DOGE/USDT",
        "signal": "REJECT",
        "judge": "REJECTED",
        "ai_conf": 40,
        "reasoning": "Price action is choppy. No clear trend direction. Social sentiment is mixed.",
        "judge_note": "AI Confidence (40%) below threshold (75%). Trade blocked."
    }
]

for log in mock_logs:
    with st.expander(f"{log['time']} | {log['signal']} {log['symbol']} | Status: {log['judge']}"):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### ⚖️ The Judge's Verdict")
            if log['judge'] == "APPROVED":
                st.success(log['judge_note'])
            else:
                st.error(log['judge_note'])
        with c2:
            st.markdown(f"### 🧠 AI Analysis ({log['ai_conf']}%)")
            st.info(log['reasoning'])

# --- 4. THE LAB ---
st.subheader("🧪 The Lab (Configuration)")
with st.form("config_form"):
    c1, c2 = st.columns(2)
    with c1:
        st.number_input("Max Risk Per Trade (%)", value=2.0)
        st.number_input("RSI Overbought Threshold", value=70)
    with c2:
        st.number_input("AI Minimum Confidence", value=75)
        st.number_input("Max Open Slots", value=5)
    
    st.form_submit_button("Update Configuration")
