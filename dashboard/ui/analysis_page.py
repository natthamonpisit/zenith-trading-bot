import streamlit as st
import pandas as pd
from src.roles.job_ai_analyst import Strategist

def render_analysis_page(db):
    st.markdown("### 📊 AI Performance Analysis Report")
    
    with st.container(border=True):
        c1, c2 = st.columns([3, 1])
        with c1: days = st.slider("Select Date Range (Days)", 1, 30, 7)
        with c2: 
            st.markdown("<br>", unsafe_allow_html=True)
            gen_btn = st.button("✨ Generate", type="primary", use_container_width=True)
            
        try:
            trade_data = db.table("trade_signals").select("*, assets(symbol)").order("created_at", desc=True).limit(days * 20).execute()
            if trade_data.data:
                df = pd.DataFrame(trade_data.data)
                df['symbol'] = df['assets'].apply(lambda x: x['symbol'] if x else 'UNKNOWN')
                st.dataframe(df[['created_at', 'symbol', 'signal_type', 'status']].head(10), use_container_width=True)
                
                if gen_btn:
                    with st.spinner("🤖 Analyzing..."):
                        strat = Strategist()
                        clean_history = df[['created_at', 'symbol', 'signal_type', 'status', 'judge_reason']].to_dict(orient='records')
                        report = strat.generate_performance_report(clean_history, days)
                        st.markdown("---")
                        st.success("Analysis Complete!")
                        st.markdown(report)
            else: st.warning("No trade data found in this range.")
        except Exception as e: st.error(f"Error: {e}")
