import streamlit as st
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db
from dashboard.ui.sidebar import render_sidebar
from dashboard.ui.dashboard_page import render_dashboard_page
from dashboard.ui.config_page import render_config_page
from dashboard.ui.history_page import render_history_page
from dashboard.ui.simulation_page import render_simulation_page
from dashboard.ui.status_page import render_status_page
from dashboard.ui.analysis_page import render_analysis_page
from dashboard.ui.fundamental_page import render_fundamental_page

# --- CONFIG ---
st.set_page_config(page_title="Zenith AI Bot", layout="wide", page_icon="🤖")
db = get_db()

# Dashboard password from environment variable (default for dev only)
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "zenith2026")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; background-color: #0E1117; }
    div[data-testid="stVerticalBlockBorderWrapper"] { background-color: #1c1c1e; border-radius: 12px; padding: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); border: 1px solid #2c2c2e; }
    h1, h2, h3, h4, h5 { color: #fff !important; font-weight: 600; }
    section[data-testid="stSidebar"] { background-color: #121212; border-right: 1px solid #333; }
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE ---
if 'page' not in st.session_state: st.session_state.page = 'Dashboard'
if 'entered' not in st.session_state: st.session_state.entered = False
if 'authenticated' not in st.session_state: st.session_state.authenticated = False

# --- AUTHENTICATION ---
if not st.session_state.authenticated:
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<br>"*3, unsafe_allow_html=True)
        st.markdown("<div style='text-align: center;'> <h1 style='font-size: 80px;'>🐺</h1> <h1>ZENITH OS</h1> <p style='color: grey;'>AI Trading Modular Gateway</p> </div>", unsafe_allow_html=True)
        password = st.text_input("Enter Password", type="password", placeholder="Dashboard password")
        if st.button("🔐 LOGIN", type="primary", use_container_width=True):
            if password == DASHBOARD_PASSWORD:
                st.session_state.authenticated = True
                st.session_state.entered = True
                st.rerun()
            else:
                st.error("Invalid password.")
    st.stop()

# --- GATEKEEPER ---
if not st.session_state.entered:
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<br>"*5, unsafe_allow_html=True)
        st.markdown("<div style='text-align: center;'> <h1 style='font-size: 80px;'>🐺</h1> <h1>ZENITH OS</h1> <p style='color: grey;'>AI Trading Modular Gateway</p> </div>", unsafe_allow_html=True)
        if st.button("🔌 CONNECT TO SYSTEM", type="primary", use_container_width=True):
            st.session_state.entered = True
            st.rerun()
    st.stop()

from dashboard.ui.farming_page import render_farming_page
import time

# --- GATEKEEPER (Farming Check) ---
# Check if data is fresh (within 12 hours)
is_fresh = False
try:
    last_farm = db.table("bot_config").select("value").eq("key", "LAST_FARM_TIME").execute()
    if last_farm.data:
        elapsed = time.time() - float(last_farm.data[0]['value'])
        if elapsed < 43200: # 12 Hours
            is_fresh = True
except: pass

if not is_fresh and not st.session_state.get('farming_complete'):
    render_farming_page(db)
    st.stop() # Stop here, don't show dashboard

# --- MODULE ROUTING ---
render_sidebar(db)

if st.session_state.page == 'Dashboard':
    render_dashboard_page(db)
elif st.session_state.page == 'Strategy Config':
    render_config_page(db)
elif st.session_state.page == 'Trade History':
    render_history_page(db)
elif st.session_state.page == 'Simulation Mode':
    render_simulation_page(db)
elif st.session_state.page == 'System Status':
    render_status_page(db)
elif st.session_state.page == 'Analyze Report':
    render_analysis_page(db)

# --- AUTO REFRESH LOGIC ---
if st.session_state.get('auto_refresh'):
    import time
    time.sleep(10)
    st.rerun()
