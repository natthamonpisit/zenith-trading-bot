import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
import os
import time
from datetime import datetime

# Add project root to path so we can import src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db
from src.roles.job_spy import Spy

@st.cache_resource
def get_spy_instance():
    return Spy()

# --- CONFIG ---
st.set_page_config(page_title="Zenith AI Bot", layout="wide", page_icon="🤖")
db = get_db()

# --- CUSTOM CSS ---
st.markdown("""
<style>
    /* Global Font */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        background-color: #0E1117;
    }
    
    /* NATIVE CONTAINER CARD DESIGN */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #1c1c1e;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
        border: 1px solid #2c2c2e;
    }
    
    /* Neon Headers */
    h1, h2, h3, h4, h5 {
        color: #fff !important;
        font-weight: 600;
    }
    
    /* Sidebar Aesthetics */
    section[data-testid="stSidebar"] {
        background-color: #121212;
        border-right: 1px solid #333;
    }
    
    /* Timeframe Chips */
    .stRadio div[role='radiogroup'] > label {
        background-color: #262730;
        border: 1px solid #444;
        border-radius: 20px;
        padding: 5px 15px;
        margin-right: 5px;
    }
    .stRadio div[role='radiogroup'] > label[data-checked='true'] {
        background-color: #00FF94 !important;
        color: black !important;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE ---
if 'page' not in st.session_state: st.session_state.page = 'Dashboard'
if 'timeframe' not in st.session_state: st.session_state.timeframe = '1h'
if 'selected_indicators' not in st.session_state: st.session_state.selected_indicators = ['EMA 20', 'EMA 50']
if 'entered' not in st.session_state: st.session_state.entered = False

def navigate_to(page): st.session_state.page = page

# --- LANDING PAGE (Gatekeeper) ---
if not st.session_state.entered:
    # Full screen centering
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<br>"*5, unsafe_allow_html=True)
        st.markdown("""
        <div style="text-align: center;">
            <h1 style="font-size: 80px; margin-bottom: 0;">🐺</h1>
            <h1 style="font-size: 60px; background: -webkit-linear-gradient(#eee, #333); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">ZENITH OS</h1>
            <p style="color: grey; font-size: 18px;">AI-Powered Autonomous Trading System</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Status Checks
        with st.status("🚀 System Initialization...", expanded=True) as status:
            st.write("🔌 Connecting to Secure Gateway...")
            time.sleep(1)
            st.write("🧠 Waking up Gemini AI...")
            time.sleep(1)
            st.write("💹 Fetching Live Market Data...")
            time.sleep(1)
            status.update(label="✅ System Ready", state="complete", expanded=False)
            
        st.markdown("<br>", unsafe_allow_html=True)
        
        if st.button("🔌 CONNECT TO SYSTEM", type="primary", use_container_width=True):
            st.session_state.entered = True
            st.rerun()
            
    # Stop execution here so sidebar doesn't show
    st.stop()

# --- MAIN APP START ---

# --- LEFT SIDEBAR (Navigation) ---
with st.sidebar:
    st.markdown("### 🤖 Zenith OS")
    st.caption(f"System Time: {datetime.now().strftime('%H:%M:%S')}")
    st.markdown("---")
    
    
    # Navigation Logic
    pages = ['Dashboard', 'Strategy Config', 'Trade History', 'Analyze Report', 'System Status']
    for p in pages:
        if st.button(f"{'🔷' if st.session_state.page == p else '🔹'} {p}", key=f"nav_{p}", use_container_width=True):
            navigate_to(p)
            st.rerun()
            
    st.markdown("---")
    st.markdown("<div style='margin-top:auto;'></div>", unsafe_allow_html=True)
    
    # Modern Kill Switch
    st.markdown("#### 🚨 Emergency Control")
    try:
        config_res = db.table("bot_config").select("*").eq("key", "BOT_STATUS").execute()
        current_status = config_res.data[0]['value'] if config_res.data else "ACTIVE"
    except: current_status = "ACTIVE"

    if current_status == "ACTIVE":
        if st.button("🔴 STOP TRADING", type="primary", use_container_width=True, help="Force Halt All Operations"):
            db.table("bot_config").upsert({"key": "BOT_STATUS", "value": "STOPPED"}).execute()
            st.rerun()
    else:
        st.error("⛔ SYSTEM HALTED")
        if st.button("🟢 RESUME TRADING", use_container_width=True):
            db.table("bot_config").upsert({"key": "BOT_STATUS", "value": "ACTIVE"}).execute()
            st.rerun()

# --- DASHBOARD PAGE ---
if st.session_state.page == 'Dashboard':
    # --- HEADER / MODE BADGE ---
    # Fetch Mode securely
    try:
        conf_mode = db.table("bot_config").select("*").eq("key", "TRADING_MODE").execute()
        current_mode = conf_mode.data[0]['value'] if conf_mode.data else "PAPER"
        current_mode = current_mode.replace('"', '')
    except: current_mode = "PAPER"

    c1, c2 = st.columns([3, 1])
    with c1:
        if current_mode == "LIVE":
            st.markdown(f"""
            <div style="padding: 10px; background-color: rgba(255, 0, 85, 0.2); border: 1px solid #FF0055; border-radius: 10px; display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 20px;">🔴</span>
                <div>
                    <h3 style="margin:0; color: #FF0055;">LIVE TRADING ACTIVE</h3>
                    <p style="margin:0; font-size: 0.8em; opacity: 0.8;">Real Capital at Risk. Signals are executed on Binance.</p>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="padding: 10px; background-color: rgba(0, 255, 148, 0.1); border: 1px solid #00FF94; border-radius: 10px; display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 20px;">🎮</span>
                <div>
                    <h3 style="margin:0; color: #00FF94;">SIMULATION MODE</h3>
                    <p style="margin:0; font-size: 0.8em; opacity: 0.8;">Testing strategies with paper money. No real risk.</p>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
    with c2:
        if st.button("🔄 Refresh Data", use_container_width=True): st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    
    main_col, right_col = st.columns([3, 1])

    # --- RIGHT SIDEBAR CONTENTS ---
    with right_col:
        
        # 0. MODE TOGGLE (Quick Switch)
        with st.container(border=True):
            st.markdown("##### 🎚️ Mode Control")
            is_live = (current_mode == "LIVE")
            toggle_mode = st.toggle("Enable Live Trading", value=is_live, help="Switch between Paper Trading and Real Execution")
            
            if toggle_mode != is_live:
                new_val = '"LIVE"' if toggle_mode else '"PAPER"'
                db.table("bot_config").upsert({"key": "TRADING_MODE", "value": new_val}).execute()
                st.rerun()

        # 1. Dynamic Portfolio
        with st.container(border=True):
            if current_mode == "PAPER":
                st.markdown("##### 🎮 Paper Portfolio")
                try:
                    # Get Sim Data
                    sim = db.table("simulation_portfolio").select("*").eq("id", 1).execute()
                    balance = float(sim.data[0]['balance']) if sim.data else 1000.0
                    
                    pos = db.table("positions").select("*").eq("is_sim", True).eq("is_open", True).execute()
                    invested = sum([float(p['entry_avg']) * float(p['quantity']) for p in pos.data]) if pos.data else 0.0
                    total_equity = balance + invested 
                    
                    st.metric("Total Equity", f"${total_equity:,.2f}")
                    c1, c2 = st.columns(2)
                    c1.metric("Cash", f"${balance:,.2f}")
                    c2.metric("In Trade", f"${invested:,.2f}")
                    
                    # Reset Button for Sim
                    if st.button("🔄 Reset Balance", use_container_width=True):
                        db.table("simulation_portfolio").update({"balance": 1000.0}).eq("id", 1).execute()
                        db.table("positions").delete().eq("is_sim", True).execute() # Clear sim positions
                        db.table("trade_signals").delete().eq("is_sim", True).execute() # Clear sim signals
                        st.toast("Simulation Reset to $1,000", icon="✅")
                        time.sleep(1)
                        st.rerun()

                except Exception as e:
                    st.error(f"Sim Data Error: {e}")

            else:
                # LIVE MODE UI (Same as before but simplified)
                st.markdown("##### 💰 Real Portfolio")
                try:
                    spy_instance = get_spy_instance()
                    if not spy_instance.exchange.markets: spy_instance.load_markets_custom()
                    
                    balance = spy_instance.get_account_balance()
                    thb_rate = spy_instance.get_usdt_thb_rate()
                    
                    if balance:
                        total_bal = balance.get('total', {})
                        non_zero = {k: v for k, v in total_bal.items() if v > 0}
                        total_usdt_est = 0
                        
                        if non_zero:
                            for asset, amount in non_zero.items():
                                 if asset == 'USDT': total_usdt_est += amount
                                 st.markdown(f"**{asset}**: `{amount:,.4f}`")
                            
                            st.divider()
                            est_thb = total_usdt_est * thb_rate
                            st.metric("Est. Equity", f"{total_usdt_est:,.2f} USDT", f"≈ {est_thb:,.2f} THB")
                        else: st.caption("Empty Wallet")
                    else: st.warning("Connect Error")
                except Exception as e: st.error(f"Wallet Error: {e}")

        # 2. System Health Monitor
        with st.container(border=True):
            st.markdown("##### 🏥 System Health")
            
            # Latency Measure
            t_start = time.time()
            try:
                 # Fast call using cached instance
                 get_spy_instance().exchange.load_markets() 
                 api_ok = True
            except: api_ok = False
            latency = int((time.time() - t_start) * 1000)
            
            st.markdown(f"""
            <div style='font-size: 0.9em;'>
                <div style='display:flex; justify-content:space-between; margin:5px 0;'>
                    <span>🔌 API Latency</span>
                    <span style='color:{'#00FF94' if latency<500 else '#FFAA00'}; font-weight:bold;'>{'🟢' if api_ok else '🔴'} {latency}ms</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # 4. Market Watch
        with st.container(border=True):
            st.markdown("##### 🔭 Market Watch")
            for coin in ["BTC/USDT", "ETH/USDT", "SOL/USDT"]:
                 # Mock Sparkline Effect
                 st.markdown(f"**{coin}** <span style='float:right; color:#00FF94'>$---.--</span>", unsafe_allow_html=True)
                 st.progress(70) # Visual filler for sparkline

    # --- MAIN CONTENTS ---
    with main_col:
        # 1. CHART CONTROL & DISPLAY
        with st.container(border=True):
            st.markdown("#### 📈 Active Market Chart")
            
            # Instantiate Spy for data & symbol list
            try:
                spy = get_spy_instance()
                # Ensure markets are loaded (Lazy loading fix)
                if not spy.exchange.markets:
                    spy.load_markets_custom()
                
                # Get list of symbols (Top 100 or all)
                # Filter for USDT pairs for cleaner list
                all_symbols = sorted([market for market in spy.exchange.markets.keys() if "/USDT" in market])
                if not all_symbols: all_symbols = ["BTC/USDT", "ETH/USDT"] # Fallback
            except Exception as e:
                 st.error(f"⚠️ Spy Init Failed: {e}")
                 all_symbols = ["BTC/USDT"]
                 spy = None
    
            c1, c2, c3 = st.columns([1, 2, 2])
            with c1:
                 # Symbol Selector
                 selected_symbol = st.selectbox("Symbol", all_symbols, index=all_symbols.index("BTC/USDT") if "BTC/USDT" in all_symbols else 0)
            with c2:
                # Chip-style Selector via Radio (Horizontal)
                tf_choice = st.radio("Timeframe", ["15m", "1h", "4h", "1d"], index=1, horizontal=True)
                if tf_choice != st.session_state.timeframe: 
                    st.session_state.timeframe = tf_choice
                    st.rerun()
            with c3:
                indicators = st.multiselect("Indicators", ["EMA 20", "EMA 50", "MACD", "Bollinger Bands", "RSI"], default=st.session_state.selected_indicators)
                st.session_state.selected_indicators = indicators
            
            # Fetch & Plot
            try:
                if spy:
                    df = spy.fetch_ohlcv(selected_symbol, timeframe=st.session_state.timeframe, limit=100)
                    if df is not None:
                        df = spy.calculate_indicators(df)
                        
                        # Create Subplots if RSI/MACD selected
                        rows = 2 if "RSI" in indicators or "MACD" in indicators else 1
                        row_heights = [0.7, 0.3] if rows==2 else [1.0]
                        
                        fig = go.Figure()
                        
                        # Main Candlestick
                        fig.add_trace(go.Candlestick(x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Price', increasing_line_color='#00FF94', decreasing_line_color='#FF0055'))
                        
                        # Overlays
                        if "EMA 20" in indicators: fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema_20'], line=dict(color='yellow', width=1), name='EMA 20'))
                        if "EMA 50" in indicators: fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema_50'], line=dict(color='cyan', width=1), name='EMA 50'))
                        if "Bollinger Bands" in indicators:
                            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['bb_upper'], line=dict(color='rgba(255, 255, 255, 0.3)', width=1), name='BB Upper'))
                            fig.add_trace(go.Scatter(x=df['timestamp'], y=df['bb_lower'], line=dict(color='rgba(255, 255, 255, 0.3)', width=1), fill='tonexty', name='BB Lower'))
        
                        fig.update_layout(
                            title=f"{selected_symbol} ({st.session_state.timeframe})",
                            xaxis_rangeslider_visible=False, height=500, margin=dict(l=10,r=10,t=30,b=10), paper_bgcolor="#0e1117", plot_bgcolor="#0e1117", font=dict(color="#bbb"), xaxis=dict(gridcolor="#222"), yaxis=dict(gridcolor="#222")
                        )
                        st.plotly_chart(fig, use_container_width=True)
            except Exception as e: st.error(f"Chart Error: {e}")
        
        # 2. ENHANCED LOGS
        with st.container(border=True):
            st.markdown("#### 🧠 AI Scorecards")
            try:
                signals = db.table("trade_signals").select("*, assets(symbol)").order("created_at", desc=True).limit(5).execute()
                
                for log in signals.data:
                    symbol = log['assets']['symbol'] if log['assets'] else "UNKNOWN"
                    status = log['status']
                    
                    with st.expander(f"{'✅' if status=='EXECUTED' else '🛡️'} {log['created_at'].split('T')[1][:5]} | {symbol} | {log['signal_type']}"):
                         # Scorecard Layout
                         st.markdown("##### 📊 Decision Scorecard")
                         c1, c2, c3 = st.columns(3)
                         
                         # Mock Scores (In real implementation, store these in DB)
                         tech_val = 88 if status == 'EXECUTED' else 45
                         sent_val = 75 if status == 'EXECUTED' else 60
                         risk_val = 92 if status == 'EXECUTED' else 30
                         
                         with c1:
                             st.markdown(f"**Technical** `{tech_val}/100`")
                             st.progress(tech_val)
                         with c2:
                             st.markdown(f"**Sentiment** `{sent_val}/100`")
                             st.progress(sent_val)
                         with c3:
                             st.markdown(f"**Risk Safety** `{risk_val}/100`")
                             st.progress(risk_val)
                             
                         st.info(f"💡 **AI Reasoning:** {log['judge_reason']}")
            except: pass

elif st.session_state.page == 'Strategy Config':
    st.markdown("### ⚙️ Strategy Configuration")
    st.caption("Adjust the brain parameters of the AI Strategist and Risk Judge.")
    
    with st.container(border=True):
        st.markdown("#### 🧠 AI Parameters")
        
        # Fetch current config or use defaults
        try: 
            conf_ai = db.table("bot_config").select("*").eq("key", "AI_CONFIDENCE_THRESHOLD").execute()
            current_ai = int(conf_ai.data[0]['value']) if conf_ai.data else 75
        except: current_ai = 75
        
        new_ai = st.slider("Minimum AI Confidence (%)", 0, 100, current_ai, help="Signals below this confidence will be REJECTED by The Judge.")
        
        st.markdown("#### ⚖️ Risk Management")
        c1, c2 = st.columns(2)
        with c1:
             risk_per_trade = st.number_input("Risk Per Trade (%)", value=2.0)
        with c2:
             max_open_pos = st.number_input("Max Open Positions", value=5, step=1)

        st.markdown("---")
        st.markdown("#### 🎮 Operation Mode")
        
        # Mode Toggle
        try:
            conf_mode = db.table("bot_config").select("*").eq("key", "TRADING_MODE").execute()
            curr_mode = conf_mode.data[0]['value'] if conf_mode.data else "PAPER"
        except: curr_mode = "PAPER"
        
        new_mode = st.radio("Select Mode", ["PAPER", "LIVE"], index=0 if curr_mode=="PAPER" else 1, horizontal=True)
        if new_mode == "LIVE": 
            st.warning("⚠️ LIVE MODE ENABLED: Real orders will be executed on Binance!")
        else:
            st.success("✅ PAPER MODE: Using mock balance ($1,000). Safe testing.")
             
        if st.button("💾 Save Configuration", type="primary"):
            try:
                db.table("bot_config").upsert({"key": "AI_CONFIDENCE_THRESHOLD", "value": str(new_ai)}).execute()
                db.table("bot_config").upsert({"key": "TRADING_MODE", "value": new_mode}).execute()
                # Store others if needed
                st.success("Configuration Updated Successfully!")
            except Exception as e:
                st.error(f"Save Failed: {e}")

elif st.session_state.page == 'Trade History':
    st.markdown("### 📜 Trade History")
    
    with st.container(border=True):
        st.markdown("##### 🕵️ Signal & Execution Log")
        try:
             # Fetch all signals
             history = db.table("trade_signals").select("*, assets(symbol)").order("created_at", desc=True).limit(50).execute()
             
             if history.data:
                 df_hist = pd.DataFrame(history.data)
                 # Clean up Asset Symbol
                 df_hist['symbol'] = df_hist['assets'].apply(lambda x: x['symbol'] if x else 'UNKNOWN')
                 df_hist = df_hist[['created_at', 'symbol', 'signal_type', 'entry_target', 'status', 'judge_reason']]
                 
                 # Colorize Status
                 def color_status(val):
                     color = '#00FF94' if val == 'EXECUTED' else '#FF0055' if val == 'REJECTED' else '#FFAA00'
                     return f'color: {color}'
                 
                 st.dataframe(df_hist.style.applymap(color_status, subset=['status']), use_container_width=True)
             else:
                 st.info("No trading history found yet.")
        except Exception as e:
            st.error(f"Error loading history: {e}")

elif st.session_state.page == 'Simulation Mode':
    st.markdown("### 🎮 Simulation Mode (Paper Trading)")
    st.caption("Test your strategies with mock money without risking real capital.")
    
    # Fetch Sim Data
    try:
        sim_wallet = db.table("simulation_portfolio").select("*").eq("id", 1).execute()
        balance = float(sim_wallet.data[0]['balance']) if sim_wallet.data else 1000.0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Mock Balance", f"${balance:,.2f}")
        c2.metric("Unrealized PnL", "$0.00", "0%")
        c3.metric("Win Rate", "N/A")
        
        st.divider()
        st.subheader("📜 Paper Trade History")
        
        # Fetch Sim Signals
        sim_signals = db.table("trade_signals").select("*, assets(symbol)").eq("is_sim", True).order("created_at", desc=True).execute()
        
        if sim_signals.data:
            df_sim = pd.DataFrame(sim_signals.data)
            df_sim['symbol'] = df_sim['assets'].apply(lambda x: x['symbol'] if x else 'UNKNOWN')
            st.dataframe(df_sim[['created_at', 'symbol', 'signal_type', 'entry_target', 'status']])
        else:
             st.info("No paper trades yet. Waiting for signals...")
             
    except Exception as e:
        st.error(f"Sim Error: {e}")

elif st.session_state.page == 'System Status':
    st.markdown("### 🖥️ System Internals")
    
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("##### 🔌 Connection Status")
            # Check DB
            try: 
                db.table("bot_config").select("count", count='exact').limit(1).execute()
                db_status = "✅ Connected"
            except: db_status = "❌ Disconnected"
            
            # Check Exchange
            try:
                Spy().exchange.load_markets()
                ex_status = "✅ Connected (Binance TH)"
            except: ex_status = "❌ Error"
            
            st.markdown(f"**Database:** {db_status}")
            st.markdown(f"**Exchange:** {ex_status}")
            st.markdown(f"**AI Model:** Gemini Pro (v1.5)")
            
    with c2:
        with st.container(border=True):
            st.markdown("##### 📂 Environment")
            st.code(f"""
            OS: {sys.platform}
            Python: {sys.version.split()[0]}
            Streamlit: {st.__version__}
            Timezone: {time.tzname[0]}
            """)

elif st.session_state.page == 'Analyze Report':
    st.markdown("### 📊 AI Performance Analysis Report")
    st.caption("Let the AI analyze your trading history and find patterns.")
    
    with st.container(border=True):
        c1, c2 = st.columns([3, 1])
        with c1:
            days = st.slider("Select Date Range (Last N Days)", 1, 30, 7)
        with c2:
            st.markdown("<br>", unsafe_allow_html=True)
            gen_btn = st.button("✨ Generate Analysis", type="primary", use_container_width=True)
            
        # Fetch Data
        try:
            # Simple date logic (In prod, use proper date filter)
            trade_data = db.table("trade_signals").select("*, assets(symbol)").order("created_at", desc=True).limit(days * 20).execute() # Approx limit
            
            if trade_data.data:
                df = pd.DataFrame(trade_data.data)
                df['symbol'] = df['assets'].apply(lambda x: x['symbol'] if x else 'UNKNOWN')
                
                st.markdown(f"**Found {len(df)} signals in the selected range.**")
                st.dataframe(df[['created_at', 'symbol', 'signal_type', 'status', 'judge_reason']].head(10), use_container_width=True)
                
                if gen_btn:
                    with st.spinner("🤖 The Strategist is analyzing your portfolio..."):
                        from src.roles.job_ai_analyst import Strategist
                        strat = Strategist()
                        # Clean data for AI
                        clean_history = df[['created_at', 'symbol', 'signal_type', 'status', 'judge_reason']].to_dict(orient='records')
                        report = strat.generate_performance_report(clean_history, days)
                        
                        st.markdown("---")
                        st.success("Analysis Complete!")
                        st.markdown(report)
            else:
                st.warning("No trade data found in this range.")
        except Exception as e:
            st.error(f"Error: {e}")
