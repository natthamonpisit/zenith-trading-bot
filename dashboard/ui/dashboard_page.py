import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import pytz
from .utils import get_spy_instance, get_cfg, to_local_time, sanitize

def render_dashboard_page(db):
    """Main dashboard page"""
    
    # Continue with dashboard rendering
    current_mode = get_cfg(db, "TRADING_MODE", "PAPER").replace('"', '')

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
                    <p style="margin:0; font-size: 0.8em; opacity: 0.8;">Go to 'Simulation Mode' page to see detailed paper stats.</p>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
    with c2:
        if st.button("🔄 Refresh Data", use_container_width=True): st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    
    with st.expander("📡 Live Activity Feed", expanded=True):
        try:
             logs = db.table("system_logs").select("*").order("created_at", desc=True).limit(5).execute()
             if logs.data:
                 for log in logs.data:
                     ts = to_local_time(log['created_at'], '%H:%M:%S')
                     color = "red" if log['level'] == "ERROR" else "orange" if log['level'] == "WARNING" else "#00FF94" if log['level'] == "SUCCESS" else "#ccc"
                     st.markdown(f"<code style='color:#666'>{sanitize(ts)}</code> **{sanitize(log['role'])}**: <span style='color:{color}'>{sanitize(log['message'])}</span>", unsafe_allow_html=True)
             else: st.info("Waiting for bot activity...")
        except Exception: st.caption("Log Connection Pending...")

    main_col, right_col = st.columns([3, 1])

    with right_col:
        with st.container(border=True):
            st.markdown("##### 🎚️ Mode Control")
            toggle_mode = st.toggle("Enable Live Trading", value=(current_mode == "LIVE"))
            if toggle_mode != (current_mode == "LIVE"):
                db.table("bot_config").upsert({"key": "TRADING_MODE", "value": f'"{ "LIVE" if toggle_mode else "PAPER" }"'}).execute()
                st.rerun()

        with st.container(border=True):
            st.markdown(f"##### 💰 {'Real' if current_mode=='LIVE' else 'Paper'} Portfolio")
            try:
                if current_mode == "LIVE":
                    spy = get_spy_instance()
                    balance = spy.get_account_balance()
                    if balance:
                        usdt = balance.get('total', {}).get('USDT', 0.0)
                        st.metric("Available USDT", f"${usdt:,.2f}")
                    else: st.warning("Wallet Error")
                else:
                    sim = db.table("simulation_portfolio").select("balance").eq("id", 1).execute()
                    bal = sim.data[0]['balance'] if sim.data else 1000.0
                    st.metric("Mock Balance", f"${bal:,.2f}")
            except Exception: st.error("Connection Error")

        with st.container(border=True):
            st.markdown("##### 🔭 Market Watch")
            try:
                spy = get_spy_instance()
                for coin in ["BTC/USDT", "ETH/USDT", "SOL/USDT"]:
                    ticker = spy.exchange.fetch_ticker(coin)
                    color = "#00FF94" if ticker.get('percentage', 0) >= 0 else "#FF0055"
                    st.markdown(f"**{coin}** <span style='float:right; color:{color}'>${ticker['last']:,.2f}</span>", unsafe_allow_html=True)
            except Exception as e:
                st.caption(f"Market data unavailable: {e}")

        # P&L Summary Card
        with st.container(border=True):
            st.markdown("##### 📈 Realized P&L")
            try:
                is_sim = (current_mode == "PAPER")
                closed = db.table("positions").select("pnl").eq("is_sim", is_sim).eq("is_open", False).execute()

                if closed.data:
                    pnl_values = [float(p['pnl']) for p in closed.data if p.get('pnl') is not None]
                    if pnl_values:
                        total_pnl = sum(pnl_values)
                        wins = len([p for p in pnl_values if p > 0])
                        total_trades = len(pnl_values)
                        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

                        pnl_color = "#00FF94" if total_pnl >= 0 else "#FF4B4B"
                        st.markdown(f"<h3 style='color:{pnl_color}; margin:0;'>${total_pnl:,.2f}</h3>", unsafe_allow_html=True)
                        st.caption(f"Win Rate: {win_rate:.1f}% ({wins}/{total_trades})")
                    else:
                        st.caption("No closed trades yet")
                else:
                    st.caption("No closed trades yet")
            except Exception as e:
                st.caption(f"P&L unavailable: {e}")

    with main_col:
        with st.container(border=True):
             st.markdown("#### 📈 Active Market Chart")
             render_chart_section()

        # UNIFIED HOLDINGS VIEW (filtered by current mode)
        render_active_holdings(db, current_mode)
        
        # 6-ROLE LIVE STATUS
        render_role_cards(db)

def render_role_cards(db):
    st.markdown("#### 🧩 Team Status (Live)")
    
    # 1. Fetch latest logs to find status for each role
    try:
        # Fetch enough recent logs to likely cover all roles (increased to 200 to cover full cycle)
        logs = db.table("system_logs").select("*").order("created_at", desc=True).limit(200).execute()
        
        roles = {
            "HeadHunter": {"icon": "📋", "desc": "Screener"},
            "Radar":      {"icon": "📡", "desc": "Scanner"},
            "Spy":        {"icon": "🕵️", "desc": "Data Collector"},
            "Strategist": {"icon": "🧠", "desc": "AI Analysis"},
            "Judge":      {"icon": "⚖️", "desc": "Risk Control"},
            "Sniper":     {"icon": "🔫", "desc": "Execution"}
        }
        
        # Parse latest state
        role_state = {r: {"msg": "Standby...", "time": "--:--", "status": "IDLE"} for r in roles}
        
        if logs.data:
            for log in logs.data:
                r = log['role']
                if r in role_state and role_state[r]['status'] == "IDLE":
                    # Found latest log for this role
                    role_state[r]['msg'] = log['message']
                    role_state[r]['time'] = to_local_time(log['created_at'], "%H:%M:%S")
                    role_state[r]['status'] = "ACTIVE"
                    role_state[r]['level'] = log['level'] # ERROR/WARNING/SUCCESS
        
        # 2. Render Grid (3 Columns x 2 Rows)
        # Row 1: HeadHunter, Radar, Spy
        c1, c2, c3 = st.columns(3)
        cols = [c1, c2, c3]
        row1_keys = ["HeadHunter", "Radar", "Spy"]
        
        for i, role in enumerate(row1_keys):
            state = role_state[role]
            meta = roles[role]
            with cols[i]:
                with st.container(border=True):
                    st.markdown(f"**{meta['icon']} {role}**")
                    st.caption(f"{meta['desc']} | 🕒 {state['time']}")
                    st.info(f"{state['msg']}")

        # Row 2: Strategist, Judge, Sniper
        c4, c5, c6 = st.columns(3)
        cols2 = [c4, c5, c6]
        row2_keys = ["Strategist", "Judge", "Sniper"]
        
        for i, role in enumerate(row2_keys):
            state = role_state[role]
            meta = roles[role]
            with cols2[i]:
                with st.container(border=True):
                    st.markdown(f"**{meta['icon']} {role}**")
                    st.caption(f"{meta['desc']} | 🕒 {state['time']}")
                    # Color code based on level
                    if state.get('level') == 'ERROR':
                        st.error(state['msg'])
                    elif state.get('level') == 'WARNING':
                        st.warning(state['msg'])
                    elif state.get('level') == 'SUCCESS':
                        st.success(state['msg'])
                    else:
                        st.info(state['msg'])

    except Exception as e:
        st.error(f"Team Status Error: {e}")

def render_active_holdings(db, current_mode="PAPER"):
    # Fetch active positions for current mode only
    is_sim = (current_mode == "PAPER")
    try:
        open_pos = db.table("positions").select("*, assets(symbol)").eq("is_open", True).eq("is_sim", is_sim).execute()
        if open_pos.data:
            st.markdown("#### ⚡ Assets in Progress")
            for p in open_pos.data:
                is_sim = p.get('is_sim', True)
                symbol = p['assets']['symbol'] if p['assets'] else "UNKNOWN"
                qty = float(p['quantity'])
                entry_price = float(p['entry_avg'])
                
                # Get Sim/Live Tag
                mode_tag = "🎮 SIM" if is_sim else "🔴 LIVE"
                mode_color = "#00FF94" if is_sim else "#FF0055"
                
                try: 
                    ticker = get_spy_instance().exchange.fetch_ticker(symbol)
                    curr_price = ticker['last']
                except Exception: curr_price = entry_price
                
                if 'created_at' in p:
                    utc_entry = datetime.fromisoformat(p['created_at'].replace('Z', '+00:00'))
                else:
                    utc_entry = datetime.now(pytz.utc) # Fallback if column missing

                duration = datetime.now(pytz.utc) - utc_entry
                dur_str = f"{duration.days}d {duration.seconds//3600}h {(duration.seconds//60)%60}m"
                
                pnl = (curr_price - entry_price) * qty
                pnl_pct = (pnl / (entry_price * qty)) * 100 if entry_price > 0 else 0
                color = "#00FF94" if pnl >= 0 else "#FF4B4B"

                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([2, 2, 2, 3])
                    with c1: 
                        st.markdown(f"**{symbol}**")
                        st.markdown(f"<span style='background-color:{mode_color}20; color:{mode_color}; padding: 2px 6px; border-radius: 4px; font-size: 0.7em;'>{mode_tag}</span>", unsafe_allow_html=True)
                    with c2: st.markdown(f"Entry: `${entry_price:,.2f}`")
                    with c3: st.markdown(f"Duration: `{dur_str}`")
                    with c4:
                        st.markdown(f"<h3 style='color:{color};'>${pnl:,.2f} ({pnl_pct:+.2f}%)</h3>", unsafe_allow_html=True)
                        trail_price = p.get('trailing_stop_price')
                        highest = p.get('highest_price_seen')
                        if trail_price:
                            st.caption(f"Trailing Stop: ${float(trail_price):,.2f} | Peak: ${float(highest):,.2f}")
                        elif highest and float(highest) > entry_price:
                            st.caption(f"Peak: ${float(highest):,.2f} (trailing not yet active)")
        else:
            # Empty State
            with st.container(border=True):
                 c1, c2 = st.columns([1, 10])
                 with c1: st.markdown("# 💤")
                 with c2: 
                     st.markdown("### No Assets in Progress")
                     st.caption("The Sniper is scanning. Active positions will appear here.")
    except Exception as e: st.error(f"Error rendering holdings: {e}")

def render_chart_section():
    try:
        spy = get_spy_instance()
        if not spy.exchange.markets: spy.load_markets_custom()
        all_symbols = sorted([m for m in spy.exchange.markets.keys() if "/USDT" in m]) or ["BTC/USDT"]
        
        c1, c2, c3 = st.columns([1, 2, 2])
        with c1: selected_symbol = st.selectbox("Symbol", all_symbols, index=0)
        with c2: tf = st.radio("Timeframe", ["15m", "1h", "4h", "1d"], index=1, horizontal=True)
        with c3: indicators = st.multiselect("Indicators", ["EMA 20", "EMA 50", "MACD", "RSI"], default=['EMA 20', 'EMA 50'])
        
        df = spy.fetch_ohlcv(selected_symbol, timeframe=tf, limit=100)
        if df is not None:
            df = spy.calculate_indicators(df)
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Price', increasing_line_color='#00FF94', decreasing_line_color='#FF0055'))
            if "EMA 20" in indicators: fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema_20'], line=dict(color='yellow', width=1), name='EMA 20'))
            if "EMA 50" in indicators: fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema_50'], line=dict(color='cyan', width=1), name='EMA 50'))
            fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
    except Exception as e: st.error(f"Chart Error: {e}")
