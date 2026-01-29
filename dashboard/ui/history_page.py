import streamlit as st
import pandas as pd
from .utils import to_local_time

def render_history_page(db):
    st.markdown("### 📜 Trade History")

    t1, t2 = st.tabs(["🎮 Simulation (Paper)", "💰 Live Trading"])

    with t1:
        render_session_history(db, is_sim=True)
        st.markdown("---")
        render_pnl_summary(db, is_sim=True)
        render_closed_positions(db, is_sim=True)
        render_signals_table(db, is_sim=True)

    with t2:
        render_session_history(db, is_sim=False)
        st.markdown("---")
        render_pnl_summary(db, is_sim=False)
        render_closed_positions(db, is_sim=False)
        render_signals_table(db, is_sim=False)


def render_session_history(db, is_sim):
    """Render expandable history of past sessions"""
    db_mode = "PAPER" if is_sim else "LIVE"
    try:
        # Fetch last 5 filtered sessions
        sessions = db.table("trading_sessions")\
            .select("*")\
            .eq("mode", db_mode)\
            .order("created_at", desc=True)\
            .limit(5)\
            .execute()

        st.markdown(f"#### 📅 Session History (Last 5)")

        if not sessions.data:
            st.info(f"No {db_mode} sessions found. If you just reset the bot, restart it to create a new session.")
            return

        for s in sessions.data:
                # Prepare Header Info
                s_name = s.get('session_name', 'Unnamed Session')
                net_pnl = float(s.get('net_pnl', 0))
                win_rate = float(s.get('win_rate', 0))
                trades = int(s.get('total_trades', 0))
                
                # Color Coding
                pnl_icon = "🟢" if net_pnl >= 0 else "🔴"
                pnl_str = f"${net_pnl:,.2f}"
                
                # Expander Label
                label = f"{pnl_icon} {s_name} | PnL: {pnl_str} | Win Rate: {win_rate:.1f}% ({trades} Trades)"
                
                with st.expander(label, expanded=False):
                    # 1. Metrics Row
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Net P&L", pnl_str)
                    c2.metric("Win Rate", f"{win_rate:.1f}%")
                    c3.metric("Profit Factor", f"{float(s.get('profit_factor', 0)):.2f}")
                    c4.metric("Max Drawdown", f"${float(s.get('max_drawdown', 0)):.2f}")
                    
                    # 2. Detailed Trade List for this Session
                    filters = db.table("positions").select("*, assets(symbol)")\
                        .eq("session_id", s['id'])\
                        .order("closed_at", desc=True)\
                        .execute()
                        
                    if filters.data:
                        render_session_trades(filters.data)
                    else:
                        st.info("No trades recorded in this session.")

    except Exception as e:
        st.error(f"Error loading session history: {e}")

def render_session_trades(positions_data):
    """Helper to render a mini positions table inside the expander"""
    if not positions_data: return

    df = pd.DataFrame(positions_data)
    df['symbol'] = df['assets'].apply(lambda x: x['symbol'] if x else 'UNKNOWN')
    df['closed_time'] = df['closed_at'].apply(lambda x: to_local_time(x, '%Y-%m-%d %H:%M') if x else 'N/A')
    df['pnl_display'] = df['pnl'].apply(lambda x: f"${float(x):,.2f}" if x else 'N/A')
    
    # Simple Exit Reason Format
    def safe_format_reason(r):
        s = str(r)
        if s.startswith("AI_SELL_SIGNAL"):
            return "🤖 AI Sell" 
        return s
    
    if 'exit_reason' in df.columns:
        df['reason'] = df['exit_reason'].apply(safe_format_reason)
    else:
        df['reason'] = 'N/A'
        
    def color_pnl(val):
        try:
             num = float(val.replace('$', '').replace(',', ''))
             return 'color: #00FF94' if num >= 0 else 'color: #FF4B4B'
        except: return ''

    st.dataframe(
        df[['closed_time', 'symbol', 'reason', 'pnl_display']].style.map(color_pnl, subset=['pnl_display']),
        column_config={
            'closed_time': 'Time',
            'symbol': 'Pair',
            'reason': 'Exit Reason',
            'pnl_display': 'PnL'
        },
        use_container_width=True,
        hide_index=True
    )


def render_pnl_summary(db, is_sim):
    """Render P&L summary metrics"""
    mode = "simulation" if is_sim else "live"
    try:
        closed = db.table("positions").select("pnl, entry_avg, exit_price").eq("is_sim", is_sim).eq("is_open", False).execute()

        if closed.data:
            pnl_values = [float(p['pnl']) for p in closed.data if p.get('pnl') is not None]

            if pnl_values:
                total_pnl = sum(pnl_values)
                wins = len([p for p in pnl_values if p > 0])
                losses = len([p for p in pnl_values if p < 0])
                win_rate = (wins / len(pnl_values) * 100) if pnl_values else 0
                best_trade = max(pnl_values)
                worst_trade = min(pnl_values)

                st.markdown(f"#### 📊 {mode.title()} Performance Summary")
                c1, c2, c3, c4, c5 = st.columns(5)

                pnl_color = "#00FF94" if total_pnl >= 0 else "#FF4B4B"
                c1.metric("Total Realized P&L", f"${total_pnl:,.2f}")
                c2.metric("Win Rate", f"{win_rate:.1f}%")
                c3.metric("Wins / Losses", f"{wins} / {losses}")
                c4.metric("Best Trade", f"${best_trade:,.2f}")
                c5.metric("Worst Trade", f"${worst_trade:,.2f}")

                st.markdown("---")
            else:
                st.info(f"No closed {mode} trades with P&L data yet.")
        else:
            st.info(f"No closed {mode} trades yet.")
    except Exception as e:
        st.warning(f"Could not load P&L summary: {e}")


def render_closed_positions(db, is_sim):
    """Render closed positions table with P&L"""
    mode = "simulation" if is_sim else "live"
    try:
        closed = db.table("positions").select("*, assets(symbol)").eq("is_sim", is_sim).eq("is_open", False).order("closed_at", desc=True).limit(100).execute()

        if closed.data:
            st.markdown(f"##### 💰 Closed Positions ({mode.title()})")
            df = pd.DataFrame(closed.data)
            df['symbol'] = df['assets'].apply(lambda x: x['symbol'] if x else 'UNKNOWN')
            df['closed_time'] = df['closed_at'].apply(lambda x: to_local_time(x, '%Y-%m-%d %H:%M') if x else 'N/A')
            df['entry'] = df['entry_avg'].apply(lambda x: f"${float(x):,.4f}" if x else 'N/A')
            df['exit'] = df['exit_price'].apply(lambda x: f"${float(x):,.4f}" if x else 'N/A')
            df['qty'] = df['quantity'].apply(lambda x: f"{float(x):.6f}" if x else 'N/A')
            df['pnl_val'] = df['pnl'].apply(lambda x: float(x) if x else 0)
            df['pnl_display'] = df['pnl'].apply(lambda x: f"${float(x):,.2f}" if x else 'N/A')

            # --- EXIT REASON FORMATTING ---
            def format_reason(reason):
                reason_str = str(reason)
                # Handle detailed AI reasons
                if reason_str.startswith("AI_SELL_SIGNAL"):
                    parts = reason_str.split(":", 1)
                    detail = parts[1].strip() if len(parts) > 1 else ""
                    return f"🤖 AI Sell{': ' + detail if detail else ''}"

                emoji_map = {
                    'AI_SELL_SIGNAL': '🤖 AI Sell',
                    'TRAILING_STOP': '📉 Trailing Stop',
                    'MANUAL_CLOSE': '👤 Manual',
                    'STOP_LOSS': '🛑 Stop Loss',
                    'TAKE_PROFIT': '🎯 Take Profit',
                    'EMERGENCY_CLOSE': '🚨 Emergency',
                    'SESSION_END': '⏹️ Session End',
                    'UNKNOWN': '❓ Unknown'
                }
                if not reason: return '❓ Unknown'
                return emoji_map.get(reason_str, reason_str)

            if 'exit_reason' in df.columns:
                 df['exit_reason_fmt'] = df['exit_reason'].apply(format_reason)
            else:
                 df['exit_reason_fmt'] = '❓ Unknown'

            # --- FILTER ---
            all_reasons = ["All"] + sorted([str(r) for r in df['exit_reason'].dropna().unique()]) if 'exit_reason' in df.columns else ["All"]
            reason_filter = st.selectbox("Filter by Exit Reason", all_reasons, key=f"filter_{mode}")

            if reason_filter != "All":
                 df = df[df['exit_reason'] == reason_filter]

            # Calculate return %
            def calc_return(row):
                try:
                    entry = float(row['entry_avg']) if row['entry_avg'] else 0
                    exit_p = float(row['exit_price']) if row['exit_price'] else 0
                    if entry > 0 and exit_p > 0:
                        return f"{((exit_p - entry) / entry * 100):+.2f}%"
                except:
                    pass
                return 'N/A'

            df['return_pct'] = df.apply(calc_return, axis=1)

            def color_pnl(val):
                try:
                    num = float(val.replace('$', '').replace(',', ''))
                    return 'color: #00FF94' if num >= 0 else 'color: #FF4B4B'
                except:
                    return ''

            st.dataframe(
                df[['closed_time', 'symbol', 'qty', 'entry', 'exit', 'exit_reason_fmt', 'pnl_display', 'return_pct']].style.map(color_pnl, subset=['pnl_display']),
                column_config={
                    'closed_time': 'Closed At',
                    'symbol': 'Symbol',
                    'qty': 'Quantity',
                    'entry': 'Entry Price',
                    'exit': 'Exit Price',
                    'exit_reason_fmt': 'Exit Reason',
                    'pnl_display': 'P&L (USDT)',
                    'return_pct': 'Return %'
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info(f"No closed {mode} positions yet.")
    except Exception as e:
        st.error(f"Error loading closed positions: {e}")


def render_signals_table(db, is_sim):
    """Render trade signals history table"""
    mode = "simulation" if is_sim else "live"
    try:
        st.markdown(f"##### 📋 Signal History ({mode.title()})")
        history = db.table("trade_signals").select("*, assets(symbol)").eq("is_sim", is_sim).order("created_at", desc=True).limit(100).execute()

        if history.data:
            df_hist = pd.DataFrame(history.data)
            df_hist['symbol'] = df_hist['assets'].apply(lambda x: x['symbol'] if x else 'UNKNOWN')
            df_hist['time_th'] = df_hist['created_at'].apply(lambda x: to_local_time(x, '%Y-%m-%d %H:%M'))
            df_hist = df_hist[['time_th', 'symbol', 'signal_type', 'entry_target', 'status', 'judge_reason']]

            def color_status(val):
                color = '#00FF94' if val == 'EXECUTED' else '#FF0055' if val == 'REJECTED' else '#FFAA00'
                return f'color: {color}'

            st.dataframe(df_hist.style.map(color_status, subset=['status']), use_container_width=True, hide_index=True)
        else:
            st.info(f"No {mode} trading signals found yet.")
    except Exception as e:
        st.error(f"Error loading {mode} history: {e}")
