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

        # Unrealized PnL - fetch tickers once and cache
        unrealized_pnl = 0.0
        open_pos = db.table("positions").select("*, assets(symbol)").eq("is_open", True).eq("is_sim", True).execute()

        # Cache ticker prices to avoid duplicate fetches
        ticker_cache = {}
        if open_pos.data:
            spy = get_spy_instance()
            for p in open_pos.data:
                try:
                    symbol = p['assets']['symbol'] if p['assets'] else None
                    if symbol and symbol not in ticker_cache:
                        ticker = spy.exchange.fetch_ticker(symbol)
                        ticker_cache[symbol] = ticker['last']
                    curr_price = ticker_cache.get(symbol, float(p['entry_avg']))
                    unrealized_pnl += (curr_price - float(p['entry_avg'])) * float(p['quantity'])
                except Exception as e:
                    print(f"Simulation PnL calc error for {p['assets']['symbol']}: {e}")

        # Fix: Use actual balance instead of hardcoded 1000
        pnl_pct = (unrealized_pnl / balance) * 100 if balance > 0 else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Mock Balance", f"${balance:,.2f}")
        c2.metric("Unrealized PnL", f"${unrealized_pnl:,.2f}", f"{pnl_pct:.2f}%")
        c3.metric("Total Equity", f"${(balance + unrealized_pnl):,.2f}")

        st.divider()
        st.subheader("🚀 Assets in Progress (Sim)")
        if open_pos.data:
            for p in open_pos.data:
                symbol = p['assets']['symbol'] if p['assets'] else "UNKNOWN"
                qty = float(p['quantity'])
                entry_price = float(p['entry_avg'])

                # Use cached ticker price instead of fetching again
                curr_price = ticker_cache.get(symbol, entry_price)
                
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

        # Show closed positions with P&L data
        closed_positions = db.table("positions").select("*, assets(symbol)").eq("is_sim", True).eq("is_open", False).order("closed_at", desc=True).limit(50).execute()

        if closed_positions.data:
            st.markdown("##### Closed Trades (with P&L)")
            closed_df = pd.DataFrame(closed_positions.data)
            closed_df['symbol'] = closed_df['assets'].apply(lambda x: x['symbol'] if x else 'UNKNOWN')
            closed_df['closed_time'] = closed_df['closed_at'].apply(lambda x: to_local_time(x) if x else 'N/A')
            closed_df['entry_avg'] = closed_df['entry_avg'].apply(lambda x: f"${float(x):,.2f}" if x else 'N/A')
            closed_df['exit_price'] = closed_df['exit_price'].apply(lambda x: f"${float(x):,.2f}" if x else 'N/A')
            closed_df['pnl_display'] = closed_df['pnl'].apply(lambda x: f"${float(x):,.2f}" if x else 'N/A')
            closed_df['return_pct'] = closed_df.apply(
                lambda r: f"{((float(r['exit_price'].replace('$','').replace(',','')) - float(r['entry_avg'].replace('$','').replace(',',''))) / float(r['entry_avg'].replace('$','').replace(',','')) * 100):.2f}%"
                if r['exit_price'] != 'N/A' and r['entry_avg'] != 'N/A' else 'N/A',
                axis=1
            )

            def color_pnl(val):
                if val == 'N/A':
                    return ''
                try:
                    num = float(val.replace('$', '').replace(',', ''))
                    return 'color: #00FF94' if num >= 0 else 'color: #FF4B4B'
                except:
                    return ''

            st.dataframe(
                closed_df[['closed_time', 'symbol', 'entry_avg', 'exit_price', 'pnl_display', 'return_pct']].style.map(color_pnl, subset=['pnl_display']),
                column_config={
                    'closed_time': 'Closed At',
                    'symbol': 'Symbol',
                    'entry_avg': 'Entry Price',
                    'exit_price': 'Exit Price',
                    'pnl_display': 'P&L',
                    'return_pct': 'Return %'
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No closed paper trades yet.")

        st.markdown("---")
        st.markdown("##### Recent Signals")
        sim_signals = db.table("trade_signals").select("*, assets(symbol)").eq("is_sim", True).eq("status", "EXECUTED").order("created_at", desc=True).limit(20).execute()
        if sim_signals.data:
            df = pd.DataFrame(sim_signals.data)
            df['symbol'] = df['assets'].apply(lambda x: x['symbol'] if x else 'UNKNOWN')
            df['time'] = df['created_at'].apply(lambda x: to_local_time(x))
            st.dataframe(df[['time', 'symbol', 'signal_type', 'entry_target', 'status']], use_container_width=True, hide_index=True)

    except Exception as e: st.error(f"Sim Error: {e}")
