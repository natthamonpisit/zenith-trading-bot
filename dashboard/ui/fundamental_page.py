import streamlit as st
import pandas as pd
from .utils import get_cfg

def render_fundamental_page(db):
    st.title("🕵️ The Head Hunter Lab")
    st.caption("Manage your Coin Whitelist/Blacklist and Fundamental Scores")

    # 1. Add New Coin
    with st.expander("➕ Add / Update Coin Status", expanded=False):
        c1, c2, c3 = st.columns([2, 2, 2])
        with c1:
            symbol = st.text_input("Symbol (e.g. BTC/USDT)").upper().strip()
        with c2:
            status = st.selectbox("Status", ["WHITELIST", "BLACKLIST", "NEUTRAL"])
        with c3:
            score = st.slider("Fundamental Score (0-10)", 0, 10, 5)
        
        notes = st.text_area("Notes", placeholder="Why this coin?")
        
        if st.button("Save to Database"):
            if symbol:
                try:
                    db.table("fundamental_coins").upsert({
                        "symbol": symbol,
                        "status": status,
                        "manual_score": score,
                        "notes": notes
                    }).execute()
                    st.success(f"Saved {symbol}!")
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("Please enter a symbol")

    st.markdown("---")

    # 2. View Tables
    try:
        # Fetch all
        rows = db.table("fundamental_coins").select("*").execute()
        if rows.data:
            df = pd.DataFrame(rows.data)
            
            # Summary Metrics
            c1, c2, c3 = st.columns(3)
            c1.metric("Whitelisted", len(df[df['status'] == 'WHITELIST']))
            c2.metric("Blacklisted", len(df[df['status'] == 'BLACKLIST']))
            c3.metric("Total Tracked", len(df))

            st.subheader("📋 Coin Database")
            
            # Filter View
            filter_status = st.radio("Filter:", ["ALL", "WHITELIST", "BLACKLIST", "NEUTRAL"], horizontal=True)
            
            if filter_status != "ALL":
                df = df[df['status'] == filter_status]
            
            st.dataframe(
                df,
                column_config={
                    "symbol": "Symbol",
                    "status": "Status",
                    "manual_score": st.column_config.ProgressColumn("Score", min_value=0, max_value=10),
                    "notes": "Notes",
                    "updated_at": "Last Updated"
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No fundamental data found. Add some coins above!")
            
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        st.info("💡 Hint: Did you run the 'fundamental_coins.sql' migration?")
