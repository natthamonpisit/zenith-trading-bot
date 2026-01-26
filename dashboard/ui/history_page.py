import streamlit as st
import pandas as pd
from .utils import to_local_time

def render_history_page(db):
    st.markdown("### 📜 Trade History")
    
    with st.container(border=True):
        st.markdown("##### 🕵️ Signal & Execution Log")
        try:
             history = db.table("trade_signals").select("*, assets(symbol)").order("created_at", desc=True).limit(50).execute()
             
             if history.data:
                 df_hist = pd.DataFrame(history.data)
                 df_hist['symbol'] = df_hist['assets'].apply(lambda x: x['symbol'] if x else 'UNKNOWN')
                 df_hist['time_th'] = df_hist['created_at'].apply(lambda x: to_local_time(x, '%Y-%m-%d %H:%M'))
                 df_hist = df_hist[['time_th', 'symbol', 'signal_type', 'entry_target', 'status', 'judge_reason']]
                 
                 def color_status(val):
                     color = '#00FF94' if val == 'EXECUTED' else '#FF0055' if val == 'REJECTED' else '#FFAA00'
                     return f'color: {color}'
                 
                 st.dataframe(df_hist.style.applymap(color_status, subset=['status']), use_container_width=True)
             else: st.info("No trading history found yet.")
        except Exception as e: st.error(f"Error loading history: {e}")
