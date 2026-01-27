import streamlit as st
import sys
import time
from .utils import get_spy_instance

def render_status_page(db):
    st.markdown("### 🖥️ System Internals")
    
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("##### 🔌 Connection Status")
            try: 
                db.table("bot_config").select("count", count='exact').limit(1).execute()
                db_status = "✅ Connected"
            except Exception: db_status = "❌ Disconnected"
            
            try:
                get_spy_instance().exchange.load_markets()
                ex_status = "✅ Connected (Binance TH)"
            except Exception: ex_status = "❌ Error"
            
            st.markdown(f"**Database:** {db_status}")
            st.markdown(f"**Exchange:** {ex_status}")
            st.markdown(f"**AI Model:** Gemini 2.0 Flash")
            
    with c2:
        with st.container(border=True):
            st.markdown("##### 📂 Environment")
            st.code(f"""
            OS: {sys.platform}
            Python: {sys.version.split()[0]}
            Streamlit: {st.__version__}
            """)
