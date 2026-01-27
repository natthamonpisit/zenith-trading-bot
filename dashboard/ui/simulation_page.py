import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
from .utils import get_spy_instance, to_local_time

def render_simulation_page(db):
    st.markdown("### 🎮 Simulation Mode (Paper Trading)")
    st.caption("Test your strategies with mock money.")
    
    try:
        sim_wallet = db.table("simulation_portfolio").select("*").eq("id", 1).execute()
        balance = float(sim_wallet.data[0]['balance']) if sim_wallet.data else 1000.0
        
        # Unrealized PnL
        unrealized_pnl = 0.0
        open_pos = db.table("positions").select("*, assets(symbol)").eq("is_open", True).eq("is_sim", True).execute()
        
        if open_pos.data:
            spy = get_spy_instance()
            for p in open_pos.data:
                try: 
                    ticker = spy.exchange.fetch_ticker(p['assets']['symbol'])
                    curr_price = ticker['last']
                    unrealized_pnl += (curr_price - float(p['entry_avg'])) * float(p['quantity'])
                except Exception as e:
                    print(f"Simulation PnL calc error for {p['assets']['symbol']}: {e}")

        c1, c2, c3 = st.columns(3)
        c1.metric("Mock Balance", f"${balance:,.2f}")
        c2.metric("Unrealized PnL", f"${unrealized_pnl:,.2f}", f"{(unrealized_pnl/1000)*100:.2f}%")
        c3.metric("Total Equity", f"${(balance + unrealized_pnl):,.2f}")
        
        st.divider()
        st.subheader("🚀 Assets in Progress (Sim)")
        if open_pos.data:
            for p in open_pos.data:
                symbol = p['assets']['symbol'] if p['assets'] else "UNKNOWN"
                qty = float(p['quantity'])
                entry_price = float(p['entry_avg'])
                
                try: 
                    ticker = get_spy_instance().exchange.fetch_ticker(symbol)
                    curr_price = ticker['last']
                except Exception: curr_price = entry_price
                
                try:
                    # Handle various timestamp formats from database
                    timestamp_str = p['created_at'].replace('Z', '+00:00')
                    # Remove timezone for parsing, then add it back
                    if '+' in timestamp_str:
                        dt_part, tz_part = timestamp_str.rsplit('+', 1)
                        utc_entry = datetime.fromisoformat(dt_part).replace(tzinfo=pytz.utc)
                    else:
                        utc_entry = datetime.fromisoformat(timestamp_str).replace(tzinfo=pytz.utc)
                except Exception as parse_err:
                    print(f"Timestamp parse error: {parse_err}, using current time")
                    utc_entry = datetime.now(pytz.utc)
                    
                local_entry = utc_entry.astimezone(pytz.timezone('Asia/Bangkok'))
                duration = datetime.now(pytz.utc) - utc_entry
                
                dur_str = f"{duration.days}d {duration.seconds//3600}h {(duration.seconds//60)%60}m"
                pnl = (curr_price - entry_price) * qty
                pnl_pct = (pnl / (entry_price * qty)) * 100 if entry_price > 0 else 0
                color = "#00FF94" if pnl >= 0 else "#FF4B4B"

                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([2, 2, 2, 3])
                    with c1: st.markdown(f"#### {symbol}"); st.caption(f"Side: **{p['side']}**")
                    with c2: st.markdown(f"**Entry**\n`${entry_price:,.2f}`")
                    with c3: st.markdown(f"**Duration**\n`{dur_str}`")
                    with c4: st.markdown(f"<h3 style='color:{color};'>${pnl:,.2f} ({pnl_pct:+.2f}%)</h3>", unsafe_allow_html=True)
                    st.caption(f"Entered at: {local_entry.strftime('%Y-%m-%d %H:%M:%S')} (BKKT)")
        else: st.info("No open positions in simulation.")

        st.divider()
        st.subheader("📜 Paper Trade History")
        sim_signals = db.table("trade_signals").select("*, assets(symbol)").eq("is_sim", True).eq("status", "EXECUTED").order("created_at", desc=True).execute()
        if sim_signals.data:
            df = pd.DataFrame(sim_signals.data)
            df['symbol'] = df['assets'].apply(lambda x: x['symbol'] if x else 'UNKNOWN')
            df['time'] = df['created_at'].apply(lambda x: to_local_time(x))
            st.dataframe(df[['time', 'symbol', 'signal_type', 'entry_target', 'status']], use_container_width=True)
             
    except Exception as e: st.error(f"Sim Error: {e}")
