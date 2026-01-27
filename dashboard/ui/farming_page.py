import streamlit as st
import time
import pandas as pd
from datetime import datetime

def render_farming_page(db):
    st.markdown("""
    <style>
        .farming-card {
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            border-radius: 16px;
            padding: 40px;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            border: 1px solid rgba(255,255,255,0.1);
        }
        .farming-status {
            font-size: 24px;
            font-weight: bold;
            color: #4CAF50;
            margin-top: 20px;
        }
    </style>
    """, unsafe_allow_html=True)

    # Header
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<div class='farming-card'>", unsafe_allow_html=True)
        st.markdown("<h1>🚜 FARMING MODE</h1>", unsafe_allow_html=True)
        st.markdown("<p>Gathering fresh market data... Please wait.</p>", unsafe_allow_html=True)
        
        # Live Farming Status
        status_ph = st.empty()
        detail_ph = st.empty()
        
        # Check active status
        try:
             res = db.table("bot_config").select("value").eq("key", "BOT_STATUS_DETAIL").execute()
             status = res.data[0]['value'].replace('"', '') if res.data else "Initializing..."
        except: status = "Connecting..."
        
        status_ph.markdown(f"<div class='farming-status'>{status}</div>", unsafe_allow_html=True)
        
        # Progress Bar Animation (Fake but reassuring) or Real if possible
        st.progress(50) # Indeterminate for now
        
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")
    
    # Historical Farming Data
    st.subheader("📜 Farming History")
    try:
        # Fetch farming history (Assuming table exists)
        # For now, we might not have data, so show placeholder logic
        res = db.table("farming_history").select("*").order("start_time", desc=True).limit(5).execute()
        if res.data:
            df = pd.DataFrame(res.data)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No farming history recorded yet.")
    except:
        st.warning("Farming History table not waiting or empty.")

    st.markdown("---")
    
    # --- TIMEZONE HELPER ---
    def to_thai_time(iso_str):
        try:
            if not iso_str: return "-"
            from datetime import datetime, timedelta
            import pytz
            
            # Parse ISO (Supabase returns ISO string)
            # Handle potential fractional seconds
            if "." in iso_str:
                dt = datetime.strptime(iso_str.split("+")[0], "%Y-%m-%dT%H:%M:%S.%f")
            else:
                dt = datetime.strptime(iso_str.split("+")[0], "%Y-%m-%dT%H:%M:%S")
                
            # Add 7 hours (Manual UTC+7 for simplicity or use pytz)
            thai_dt = dt + timedelta(hours=7)
            return thai_dt.strftime("%H:%M:%S")
        except: return iso_str

    # --- LIVE DEBUG CONSOLE ---
    st.subheader("📟 Live System Activity")
    try:
        # Fetch 20 recent logs
        logs = db.table("system_logs").select("*").order("timestamp", desc=True).limit(50).execute()
        if logs.data:
            # Container with fixed height for scrolling
            with st.container(height=300):
                for log in logs.data:
                    icon = "🟢" if log['level'] == 'INFO' else "🔴" if log['level'] == 'ERROR' else "🟡"
                    time_str = to_thai_time(log['timestamp'])
                    st.markdown(f"<div style='font-family: monospace; font-size: 13px; padding: 4px; border-bottom: 1px solid #333;'>{icon} [{time_str}] <b>{log['role']}</b>: {log['message']}</div>", unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Error fetching logs: {e}")

    # Auto-Reload to check for completion
    time.sleep(3)
    
    # Check if Farming is Done (Check LAST_FARM_TIME)
    try:
        last_farm = db.table("bot_config").select("value").eq("key", "LAST_FARM_TIME").execute()
        if last_farm.data:
            last_ts = float(last_farm.data[0]['value'])
            # If farm happened in last 5 minutes, we consider it "Just Done"
            if time.time() - last_ts < 300: # 5 min buffer
                 st.success("✅ Farming Complete! Redirecting...")
                 time.sleep(1)
                 st.session_state.farming_complete = True
                 st.rerun()
    except: pass
    
    st.rerun()
