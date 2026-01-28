import streamlit as st
import sys
import os
try:
    from dotenv import load_dotenv
    # Load environment variables (for local dev)
    load_dotenv()
except ImportError:
    pass  # Streamlit Cloud uses secrets, so dotenv is optional

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db
from dashboard.ui.sidebar import render_sidebar
from dashboard.ui.dashboard_page import render_dashboard_page
from dashboard.ui.wallet_page import render_wallet_page
from dashboard.ui.config_page import render_config_page
from dashboard.ui.history_page import render_history_page
from dashboard.ui.simulation_page import render_simulation_page
from dashboard.ui.status_page import render_status_page
from dashboard.ui.analysis_page import render_analysis_page
from dashboard.ui.fundamental_page import render_fundamental_page

# --- CONFIG ---
st.set_page_config(page_title="Zenith AI Bot", layout="wide", page_icon="🤖")
db = get_db()

# --- SESSION STATE ---
if 'page' not in st.session_state: st.session_state.page = 'Dashboard'
if 'auto_refresh' not in st.session_state: st.session_state.auto_refresh = True  # Keep enabled for real-time updates
# NOTE: password_correct is managed by auth.py - DO NOT initialize here!

# --- AUTHENTICATION ---
from dashboard.ui.auth import check_password, show_logout_button

if not check_password():
    st.stop()

# Show logout button in sidebar
show_logout_button()


# GATEKEEPER removed for Streamlit Cloud deployment
# (Farming check only needed when bot runs on same machine as dashboard)

from dashboard.ui.farming_page import render_farming_page
import time

# Skip farming check for Streamlit Cloud (bot runs on Railway, not here)
# Mark as complete so dashboard loads normally
if 'farming_complete' not in st.session_state:
    st.session_state.farming_complete = True

# --- MODULE ROUTING ---
render_sidebar(db)

if st.session_state.page == 'Dashboard':
    render_dashboard_page(db)
elif st.session_state.page == 'Wallet':
    render_wallet_page(db)
elif st.session_state.page == 'Strategy Config':
    render_config_page(db)
elif st.session_state.page == 'Fundamental Lab':
    render_fundamental_page(db)
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
