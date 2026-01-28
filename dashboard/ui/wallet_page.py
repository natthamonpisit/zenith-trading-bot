import streamlit as st
import pandas as pd
from datetime import datetime
from dashboard.ui.utils import to_local_time

def render_wallet_page(db):
    """
    Live Readiness Check - Wallet & Balance Overview
    
    NEW: Reads wallet data from database (synced by Railway bot)
    instead of direct Binance API connection
    """
    st.title("💰 Live Readiness Check")
    st.markdown("---")
    
    # Fetch wallet data from database
    st.markdown("## 📊 Wallet Balance")
    
    try:
        with st.spinner("🔄 Loading wallet data..."):
            result = db.table("wallet_balance")\
                .select("*")\
                .eq("is_active", True)\
                .order("total", desc=True)\
                .execute()
        
        if not result.data:
            st.warning("⚠️ No wallet data available")
            st.info("""
            💡 **Wallet data is synced from Railway bot every 5 minutes**
            
            If you just started the bot, please wait a few minutes for the first sync.
            """)
            return
        
        # Show last update time
        last_update = result.data[0].get('updated_at')
        if last_update:
            st.caption(f"📅 Last updated: {to_local_time(last_update, '%Y-%m-%d %H:%M:%S')}")
        
        # Convert to DataFrame
        df = pd.DataFrame(result.data)
        
        # Calculate USDT values for all assets
        try:
            import ccxt
            import os
            
            # Initialize exchange for price lookup
            api_key = os.environ.get("BINANCE_API_KEY")
            secret = os.environ.get("BINANCE_SECRET")
            api_url = os.environ.get("BINANCE_API_URL", "https://api.binance.com")
            
            if api_key and secret:
                exchange = ccxt.binance({
                    'apiKey': api_key,
                    'secret': secret,
                    'urls': {'api': {'public': api_url, 'private': api_url}},
                    'enableRateLimit': True,
                })
                
                # Calculate USD value for each asset
                total_usdt_value = 0.0
                for idx, row in df.iterrows():
                    asset = row['asset']
                    amount = float(row['total'])
                    
                    if asset == 'USDT':
                        usdt_value = amount
                    else:
                        try:
                            ticker = exchange.fetch_ticker(f"{asset}/USDT")
                            usdt_value = amount * ticker['last']
                        except:
                            usdt_value = 0.0
                    
                    df.at[idx, 'usd_value'] = usdt_value
                    total_usdt_value += usdt_value
            else:
                # Fallback: count only USDT
                total_usdt_value = df[df['asset'] == 'USDT']['total'].sum()
                
        except Exception as e:
            st.warning(f"⚠️ Could not fetch prices: {e}")
            total_usdt_value = df[df['asset'] == 'USDT']['total'].sum()
        
        # Calculate totals
        num_assets = len(df)
        largest_asset = df.iloc[0]['asset'] if len(df) > 0 else "N/A"
        
        # Display summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("💵 Total Portfolio Value", f"${total_usdt_value:,.2f} USDT")
        with col2:
            st.metric("🪙 Number of Assets", num_assets)
        with col3:
            st.metric("🏆 Largest Holding", largest_asset)
        
        st.markdown("---")
        
        # Display assets table
        st.markdown("### 📋 Asset Breakdown")
        
        # Format DataFrame for display
        display_df = df[['asset', 'free', 'locked', 'total']].copy()
        display_df.columns = ['Asset', 'Available', 'Locked', 'Total']
        
        # Format numbers
        for col in ['Available', 'Locked', 'Total']:
            display_df[col] = display_df[col].apply(lambda x: f"{float(x):.8f}")
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
    except Exception as e:
        st.error(f"❌ Failed to load wallet data: {str(e)}")
        st.info("💡 Make sure the bot on Railway is running and syncing wallet data")
        return
    
    st.markdown("---")
    
    # Live Readiness Checklist
    st.markdown("## ✅ Live Trading Readiness Checklist")
    
    # Check 1: Sufficient USDT
    usdt_balance = df[df['asset'] == 'USDT']['total'].sum() if 'USDT' in df['asset'].values else 0
    min_usdt = 100  # Minimum recommended
    
    check1 = usdt_balance >= min_usdt
    st.checkbox(
        f"💵 Sufficient USDT Balance (≥ ${min_usdt})", 
        value=check1,
        disabled=True,
        help=f"Current: ${usdt_balance:.2f} USDT"
    )
    
    # Check 2: Strategy configured
    try:
        config = db.table("bot_config").select("*").execute()
        check2 = len(config.data) > 0
    except:
        check2 = False
    
    st.checkbox(
        "⚙️ Strategy Configured", 
        value=check2,
        disabled=True,
        help="Bot configuration exists in database"
    )
    
    # Check 3: Paper mode tested
    try:
        trades = db.table("trades").select("*").eq("mode", "PAPER").execute()
        check3 = len(trades.data) > 0
    except:
        check3 = False
    
    st.checkbox(
        "🧪 Paper Mode Tested", 
        value=check3,
        disabled=True,
        help="At least one paper trade executed"
    )
    
    # Check 4: Bot is running
    try:
        import time
        hb_data = db.table("bot_config").select("value").eq("key", "LAST_HEARTBEAT").execute()
        if hb_data.data:
            last_hb = float(hb_data.data[0]['value'])
            diff = time.time() - last_hb
            check4 = diff < 120  # Bot active in last 2 minutes
        else:
            check4 = False
    except:
        check4 = False
    
    st.checkbox(
        "🤖 Bot Online", 
        value=check4,
        disabled=True,
        help="Bot must be running on Railway"
    )
    
    # Overall readiness
    all_checks = check1 and check2 and check3 and check4
    
    st.markdown("---")
    
    if all_checks:
        st.success("🎉 **You're ready for LIVE trading!**")
        st.info("💡 Remember to start with small position sizes and monitor closely")
    else:
        st.warning("⚠️ **Not ready for LIVE trading yet**")
        st.info("💡 Complete all checklist items before switching to LIVE mode")
    
    # Info about wallet sync
    with st.expander("ℹ️ About Wallet Data"):
        st.markdown("""
        ### How it works:
        
        1. **Bot on Railway** fetches Binance wallet balance every 5 minutes
        2. **Stores in Supabase** database (`wallet_balance` table)
        3. **Dashboard reads** from database instead of Binance directly
        
        **Why?** Streamlit Cloud's IP may be blocked by Binance for compliance reasons.
        This approach ensures you can always view your wallet balance on the dashboard.
        
        **Note:** Data is refreshed every 5 minutes. For real-time balance, check Binance directly.
        """)
