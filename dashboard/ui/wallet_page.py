import streamlit as st
import ccxt
import os
from datetime import datetime

def render_wallet_page(db):
    """
    Live Readiness Check - Wallet & Balance Overview
    Shows real-time Binance wallet balances and assets
    """
    st.title("💰 Live Readiness Check")
    st.markdown("---")
    
    # Get API credentials
    api_key = os.environ.get("BINANCE_API_KEY")
    secret = os.environ.get("BINANCE_SECRET")
    api_url = os.environ.get("BINANCE_API_URL", "https://api.binance.com")
    
    if not api_key or not secret:
        st.error("⚠️ Binance API credentials not found in environment variables!")
        st.info("💡 Set `BINANCE_API_KEY` and `BINANCE_SECRET` in `.env` file")
        return
    
    # Initialize exchange
    try:
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret,
            'urls': {'api': {'public': api_url, 'private': api_url}},
            'enableRateLimit': True,
        })
        
        # Test connection
        with st.spinner("🔄 Connecting to Binance..."):
            exchange.load_markets()
        
        st.success("✅ Connected to Binance successfully!")
        
    except Exception as e:
        st.error(f"❌ Failed to connect to Binance: {str(e)}")
        st.info("💡 Check your API credentials and network connection")
        return
    
    # Fetch balance
    st.markdown("## 📊 Wallet Balance")
    
    try:
        with st.spinner("🔄 Fetching balance..."):
            balance = exchange.fetch_balance()
        
        # Filter non-zero balances
        assets = []
        total_usdt_value = 0
        
        for currency, amounts in balance['total'].items():
            if amounts > 0:
                # Get USDT value
                usdt_value = 0
                if currency == 'USDT':
                    usdt_value = amounts
                else:
                    try:
                        ticker = exchange.fetch_ticker(f"{currency}/USDT")
                        usdt_value = amounts * ticker['last']
                    except:
                        usdt_value = 0
                
                assets.append({
                    'currency': currency,
                    'free': amounts,
                    'used': balance['used'].get(currency, 0),
                    'total': amounts,
                    'usdt_value': usdt_value
                })
                total_usdt_value += usdt_value
        
        # Sort by USDT value
        assets.sort(key=lambda x: x['usdt_value'], reverse=True)
        
        # Display summary
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("💵 Total Portfolio Value", f"${total_usdt_value:,.2f} USDT")
        with col2:
            st.metric("🪙 Number of Assets", len(assets))
        with col3:
            largest_asset = assets[0]['currency'] if assets else "N/A"
            st.metric("🏆 Largest Holding", largest_asset)
        
        st.markdown("---")
        
        # Display assets table
        if assets:
            st.markdown("### 📋 Asset Breakdown")
            
            for asset in assets:
                with st.expander(f"**{asset['currency']}** - ${asset['usdt_value']:,.2f} USDT ({asset['usdt_value']/total_usdt_value*100:.1f}%)"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Available", f"{asset['free']:.8f}")
                    with col2:
                        st.metric("In Orders", f"{asset['used']:.8f}")
                    with col3:
                        st.metric("Total", f"{asset['total']:.8f}")
        else:
            st.warning("⚠️ No assets found in wallet")
            st.info("💡 Deposit funds to start trading")
        
    except Exception as e:
        st.error(f"❌ Failed to fetch balance: {str(e)}")
        return
    
    st.markdown("---")
    
    # Live Readiness Checklist
    st.markdown("## ✅ Live Trading Readiness Checklist")
    
    # Check 1: Sufficient USDT
    usdt_balance = next((a['total'] for a in assets if a['currency'] == 'USDT'), 0)
    min_usdt = 100  # Minimum recommended
    
    check1 = usdt_balance >= min_usdt
    st.checkbox(
        f"💵 Sufficient USDT Balance (≥ ${min_usdt})", 
        value=check1,
        disabled=True,
        help=f"Current: ${usdt_balance:.2f} USDT"
    )
    
    # Check 2: API permissions
    try:
        exchange.fetch_my_trades(symbol='BTC/USDT', limit=1)
        check2 = True
    except:
        check2 = False
    
    st.checkbox(
        "🔑 API Trading Permissions Enabled", 
        value=check2,
        disabled=True,
        help="API key must have 'Enable Trading' permission"
    )
    
    # Check 3: Strategy configured
    try:
        config = db.table("bot_config").select("*").execute()
        check3 = len(config.data) > 0
    except:
        check3 = False
    
    st.checkbox(
        "⚙️ Strategy Configured", 
        value=check3,
        disabled=True,
        help="Bot configuration exists in database"
    )
    
    # Check 4: Paper mode tested
    try:
        trades = db.table("trades").select("*").eq("mode", "PAPER").execute()
        check4 = len(trades.data) > 0
    except:
        check4 = False
    
    st.checkbox(
        "🧪 Paper Mode Tested", 
        value=check4,
        disabled=True,
        help="At least one paper trade executed"
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
    
    # Last updated
    st.caption(f"🕐 Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
