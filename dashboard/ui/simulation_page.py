import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
from .utils import get_spy_instance, to_local_time

def render_simulation_page(db):
    st.markdown("### 🎮 Simulation Mode (Paper Trading)")
    st.caption("Test your strategies with mock money without risking real capital.")
    
    try:
        sim_wallet = db.table("simulation_portfolio").select("*").eq("id", 1).execute()
        balance = float(sim_wallet.data[0]['balance']) if sim_wallet.data else 1000.0
        
        # Calculate Unrealized PnL
        unrealized_pnl = 0.0
        open_pos = db.table("positions").select("*, assets(symbol)").eq("is_open", True).eq("is_sim", True).execute()
        
        if open_pos.data:
            spy = get_spy_instance()
            for p in open_pos.data:
                try: 
                    ticker = spy.exchange.fetch_ticker(p['assets']['symbol'])
                    curr_price = ticker['last']
                    unrealized_pnl += (curr_price - float(p['entry_avg'])) * float(p['quantity'])
                except: pass

        c1, c2, c3 = st.columns(3)
        c1.metric("Mock Balance", f"${balance:,.2f}")
        c2.metric("Unrealized PnL", f"${unrealized_pnl:,.2f}", f"{(unrealized_pnl/1000)*100:.2f}%")
        c3.metric("Total Equity", f"${(balance + unrealized_pnl):,.2f}")
        
        st.divider()
        st.subheader("🚀 Assets in Progress (Sim)")
        if open_pos.data:
            for p in open_pos.data:
                with st.container(border=True):
                    # Same rich card logic as in previous execution
                    symbol = p['assets']['symbol'] if p['assets'] else "UNKNOWN"
                    pnl = (ticker['last'] - float(p['entry_avg'])) * float(p['quantity']) # Simplified
                    st.markdown(f"**{symbol}** | PnL: `${pnl:,.2f}`")
        else: st.info("No open positions in simulation.")

        st.divider()
        st.subheader("📜 Paper Trade History")
        sim_signals = db.table("trade_signals").select("*, assets(symbol)").eq("is_sim", True).eq("status", "EXECUTED").order("created_at", desc=True).execute()
        if sim_signals.data:
            df = pd.DataFrame(sim_signals.data)
            df['symbol'] = df['assets'].apply(lambda x: x['symbol'] if x else 'UNKNOWN')
            st.dataframe(df[['created_at', 'symbol', 'signal_type', 'entry_target', 'status']], use_container_width=True)
             
    except Exception as e: st.error(f"Sim Error: {e}")
