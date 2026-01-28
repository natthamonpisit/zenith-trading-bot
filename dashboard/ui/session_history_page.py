import streamlit as st
import pandas as pd
import json
from datetime import datetime

def render_session_history_page(db):
    st.title("📊 Trading Session History")
    st.caption("View past trading sessions with detailed performance metrics and configuration snapshots")

    # Mode filter
    mode_filter = st.radio("Filter by Mode:", ["ALL", "PAPER", "LIVE"], horizontal=True)

    try:
        # Fetch sessions
        query = db.table("trading_sessions").select("*").order("started_at", desc=True)
        if mode_filter != "ALL":
            query = query.eq("mode", mode_filter)

        sessions = query.execute()

        if not sessions.data:
            st.info(f"No {mode_filter.lower() if mode_filter != 'ALL' else ''} trading sessions found.")
            return

        # Summary metrics
        all_sessions = sessions.data
        total_pnl = sum([float(s['net_pnl']) for s in all_sessions if s.get('net_pnl')])
        total_trades = sum([int(s['total_trades']) for s in all_sessions if s.get('total_trades')])

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Sessions", len(all_sessions))
        c2.metric("Total Trades", total_trades)
        pnl_color = "#00FF94" if total_pnl >= 0 else "#FF4B4B"
        c3.markdown(f"<h3 style='color:{pnl_color};'>Cumulative P&L: ${total_pnl:,.2f}</h3>", unsafe_allow_html=True)

        st.markdown("---")

        # Display each session
        for session in all_sessions:
            status_icon = "🟢" if session['is_active'] else "⚪"
            mode_icon = "🎮" if session['mode'] == 'PAPER' else "🔴"

            # Session header
            session_title = f"{status_icon} {mode_icon} {session['session_name']}"
            started = session['started_at'][:19] if session['started_at'] else "N/A"
            ended = session['ended_at'][:19] if session['ended_at'] else "Active"

            with st.expander(f"{session_title} | Started: {started}", expanded=False):
                # Metrics row
                m1, m2, m3, m4 = st.columns(4)

                net_pnl = float(session['net_pnl'])
                pnl_color = "#00FF94" if net_pnl >= 0 else "#FF4B4B"

                m1.metric("Net P&L", f"${net_pnl:,.2f}", help="Total profit/loss")
                m2.metric("Win Rate", f"{float(session['win_rate']):.1f}%", help="Percentage of winning trades")
                m3.metric("Profit Factor", f"{float(session['profit_factor']):.2f}", help="Gross profit / Gross loss")
                m4.metric("Max Drawdown", f"{float(session['max_drawdown_pct']):.1f}%", help="Largest peak-to-trough decline")

                st.markdown("---")

                # Detailed stats
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("##### 📈 Performance Details")
                    st.write(f"**Total Trades:** {session['total_trades']}")
                    st.write(f"**Winning Trades:** {session['winning_trades']}")
                    st.write(f"**Losing Trades:** {session['losing_trades']}")
                    st.write(f"**Gross Profit:** ${float(session['gross_profit']):,.2f}")
                    st.write(f"**Gross Loss:** ${float(session['gross_loss']):,.2f}")
                    st.write(f"**Largest Win:** ${float(session['largest_win']):,.2f}")
                    st.write(f"**Largest Loss:** ${float(session['largest_loss']):,.2f}")
                    st.write(f"**Avg Win:** ${float(session['avg_win']):,.2f}")
                    st.write(f"**Avg Loss:** ${float(session['avg_loss']):,.2f}")

                with col2:
                    st.markdown("##### 💰 Balance Info")
                    st.write(f"**Start Balance:** ${float(session['start_balance']):,.2f}")
                    st.write(f"**Current Balance:** ${float(session['current_balance']):,.2f}")
                    st.write(f"**Return:** {((float(session['current_balance']) - float(session['start_balance'])) / float(session['start_balance']) * 100):+.2f}%")
                    st.write(f"**Max Drawdown:** ${float(session['max_drawdown']):,.2f} ({float(session['max_drawdown_pct']):.1f}%)")

                    st.markdown("##### 📅 Timeline")
                    st.write(f"**Started:** {started}")
                    st.write(f"**Ended:** {ended}")
                    if session['ended_at']:
                        start_dt = datetime.fromisoformat(session['started_at'].replace('Z', '+00:00'))
                        end_dt = datetime.fromisoformat(session['ended_at'].replace('Z', '+00:00'))
                        duration = end_dt - start_dt
                        days = duration.days
                        hours = duration.seconds // 3600
                        st.write(f"**Duration:** {days}d {hours}h")

                st.markdown("---")

                # Config snapshot
                if session.get('config_snapshot'):
                    with st.expander("⚙️ Configuration Snapshot", expanded=False):
                        try:
                            config = session['config_snapshot']
                            if isinstance(config, str):
                                config = json.loads(config)

                            # Display key config values
                            st.json(config)
                        except Exception as e:
                            st.error(f"Could not parse config: {e}")

                # View related trades
                try:
                    positions = db.table("positions").select("*, assets(symbol)")\
                        .eq("session_id", session['id'])\
                        .eq("is_open", False)\
                        .order("closed_at", desc=True)\
                        .limit(10)\
                        .execute()

                    if positions.data and len(positions.data) > 0:
                        with st.expander(f"📋 Recent Trades ({len(positions.data)})", expanded=False):
                            df = pd.DataFrame(positions.data)
                            df['symbol'] = df['assets'].apply(lambda x: x['symbol'] if x else 'UNKNOWN')
                            df['entry'] = df['entry_avg'].apply(lambda x: f"${float(x):,.2f}")
                            df['exit'] = df['exit_price'].apply(lambda x: f"${float(x):,.2f}" if x else "N/A")
                            df['pnl'] = df['pnl'].apply(lambda x: f"${float(x):,.2f}" if x else "N/A")

                            st.dataframe(
                                df[['symbol', 'entry', 'exit', 'pnl', 'closed_at']],
                                use_container_width=True,
                                hide_index=True
                            )
                except Exception as e:
                    st.caption(f"Could not load trades: {e}")

                # Config changes during session
                try:
                    changes = db.table("config_change_log")\
                        .select("*")\
                        .eq("session_id", session['id'])\
                        .order("changed_at", desc=True)\
                        .limit(20)\
                        .execute()

                    if changes.data and len(changes.data) > 0:
                        with st.expander(f"📝 Parameter Changes ({len(changes.data)})", expanded=False):
                            df_changes = pd.DataFrame(changes.data)
                            df_changes['time'] = df_changes['changed_at'].apply(lambda x: x[:19] if x else "N/A")
                            st.dataframe(
                                df_changes[['time', 'key', 'old_value', 'new_value']],
                                use_container_width=True,
                                hide_index=True
                            )
                except Exception as e:
                    st.caption(f"No config changes recorded: {e}")

    except Exception as e:
        st.error(f"Error loading session history: {e}")
