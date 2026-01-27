import streamlit as st
import time
import datetime
import pytz
from src.database import get_db
from .utils import get_cfg, to_local_time

def render_sidebar(db):
    with st.sidebar:
        st.markdown("### 🤖 Zenith OS")
        tz_th = pytz.timezone('Asia/Bangkok')
        system_time = datetime.datetime.now(tz_th).strftime('%H:%M:%S')
        st.caption(f"System Time (TH): {system_time}")
        
        # System Heartbeat Check
        try:
            hb_data = db.table("bot_config").select("value").eq("key", "LAST_HEARTBEAT").execute()
            if hb_data.data:
                last_hb = float(hb_data.data[0]['value'])
                diff = time.time() - last_hb
                if diff < 120:
                    st.success(f"💓 System Online")
                else:
                    st.error(f"💀 Offline ({int(diff/60)}m ago)")
            else:
                st.warning("⚠️ No Heartbeat Signal")
        except Exception as e:
            st.error(f"⚠️ Connection Error: {e}")
            st.caption("Retrying DB...")
        
        st.markdown("---")
        
        # Navigation
        pages = ['Dashboard', 'Strategy Config', 'Fundamental Lab', 'Trade History', 'Analyze Report', 'System Status', 'Simulation Mode']
        for p in pages:
            if st.button(f"{'🔷' if st.session_state.page == p else '🔹'} {p}", key=f"nav_{p}", use_container_width=True):
                st.session_state.page = p
                st.rerun()
                
        st.markdown("---")
        
        # Emergency Control
        st.markdown("#### 🚨 Emergency Control")
        current_status = get_cfg(db, "BOT_STATUS", "ACTIVE").replace('"', '')
        
        c1, c2 = st.columns([3, 1])
        with c1:
            if current_status == "ACTIVE":
                if st.button("🔴 STOP TRADING", type="primary", use_container_width=True):
                    db.table("bot_config").upsert({"key": "BOT_STATUS", "value": "STOPPED"}).execute()
                    st.rerun()
            else:
                st.error("⛔ SYSTEM HALTED")
                if st.button("🟢 RESUME TRADING", use_container_width=True):
                    db.table("bot_config").upsert({"key": "BOT_STATUS", "value": "ACTIVE"}).execute()
                    st.rerun()
                    
        with c2:
            # Dangerous Button: Restart Server
            if st.button("🔄", help="Force Restart Server (Kill Process)", use_container_width=True):
                 db.table("bot_config").upsert({"key": "BOT_COMMAND", "value": "RESTART"}).execute()
                 st.toast("♻️ Restart Command Sent! Waiting for Watchdog...", icon="💀")
        
        # Auto Refresh Toggle
        if 'auto_refresh' not in st.session_state: st.session_state.auto_refresh = True
        st.session_state.auto_refresh = st.toggle("🔄 Auto Refresh (10s)", value=st.session_state.auto_refresh)

        # System Console
        st.markdown("---")
        st.markdown("#### 📟 System Console")
        try:
            console_logs = db.table("system_logs").select("*").order("created_at", desc=True).limit(15).execute()
            with st.container(height=250):
                if console_logs.data:
                    for log in console_logs.data:
                        try:
                            ts = to_local_time(log['created_at'], '%H:%M:%S')
                        except: ts = "--:--"
                        
                        c_map = {"ERROR": "#FF4B4B", "WARNING": "#FFA726", "SUCCESS": "#00FF94", "INFO": "#B0BEC5"}
                        color = c_map.get(log.get('level', 'INFO'), "#B0BEC5")
                        
                        st.markdown(f"""
                        <div style="font-family: 'Consolas', 'Courier New', monospace; font-size: 10px; line-height: 1.2; margin-bottom: 8px; border-left: 2px solid {color}; padding-left: 5px;">
                            <span style="color: #666;">{ts}</span> <b style="color: #EEE;">{log.get('role', '?')}</b><br>
                            <span style="color: {color}; word-wrap: break-word;">{log.get('message', '')}</span>
                        </div>
                        """, unsafe_allow_html=True)
                else: st.caption("No logs available")
        except: st.caption("Console Disconnected")
