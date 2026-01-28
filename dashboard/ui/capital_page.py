import streamlit as st
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.capital_manager import (
    get_allocation,
    manual_transfer,
    update_settings,
    initialize_allocation
)
from .utils import get_cfg

def render_capital_page(db):
    st.title("💰 Capital Management")
    st.caption("Protect your capital by separating trading funds from profits")

    # Get current trading mode
    try:
        mode_cfg = db.table("bot_config").select("value").eq("key", "TRADING_MODE").execute()
        current_mode = str(mode_cfg.data[0]['value']).replace('"', '').strip() if mode_cfg.data else "PAPER"
    except:
        current_mode = "PAPER"

    # Mode indicator
    mode_color = "#00FF94" if current_mode == "PAPER" else "#FF0055"
    st.markdown(f"""
    <div style="padding: 10px; background-color: {mode_color}20; border: 1px solid {mode_color}; border-radius: 10px; margin-bottom: 20px;">
        <h4 style="margin:0; color: {mode_color};">{'🎮 PAPER MODE' if current_mode == 'PAPER' else '🔴 LIVE MODE'}</h4>
        <p style="margin:0; font-size: 0.9em; opacity: 0.8;">Managing {current_mode} capital allocation</p>
    </div>
    """, unsafe_allow_html=True)

    # Get allocation data
    allocation = get_allocation(mode=current_mode)

    if not allocation:
        st.warning(f"No capital allocation found for {current_mode} mode. Initializing...")
        # Initialize with current balance
        if current_mode == "PAPER":
            sim_wallet = db.table("simulation_portfolio").select("balance").eq("id", 1).execute()
            initial = float(sim_wallet.data[0]['balance']) if sim_wallet.data else 1000.0
        else:
            # For LIVE, use a default (user can adjust later)
            initial = 1000.0

        initialize_allocation(mode=current_mode, initial_capital=initial)
        st.rerun()
        return

    # Extract values
    trading_capital = float(allocation['trading_capital'])
    profit_reserve = float(allocation['profit_reserve'])
    total_capital = trading_capital + profit_reserve

    # Actual balance (for comparison)
    if current_mode == "PAPER":
        try:
            sim_wallet = db.table("simulation_portfolio").select("balance").eq("id", 1).execute()
            actual_balance = float(sim_wallet.data[0]['balance']) if sim_wallet.data else 0.0
        except:
            actual_balance = 0.0
    else:
        try:
            from src.roles.job_price import PriceSpy
            spy = PriceSpy()
            bal_data = spy.get_account_balance()
            actual_balance = bal_data['total'].get('USDT', 0.0) if bal_data else 0.0
        except:
            actual_balance = 0.0

    # === VISUAL ALLOCATION ===
    st.markdown("### 📊 Capital Allocation")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "🎯 Trading Capital",
            f"${trading_capital:,.2f}",
            help="Amount bot is allowed to trade with"
        )

    with col2:
        st.metric(
            "🏦 Profit Reserve",
            f"${profit_reserve:,.2f}",
            help="Accumulated profits (protected from trading)"
        )

    with col3:
        st.metric(
            "💵 Actual Balance",
            f"${actual_balance:,.2f}",
            help="Real wallet balance (Paper: simulation, Live: Binance)"
        )

    # Progress bar showing allocation
    if total_capital > 0:
        trading_pct = (trading_capital / total_capital) * 100
        reserve_pct = 100 - trading_pct

        st.markdown("#### Allocation Breakdown")
        col_a, col_b = st.columns([trading_pct/100, reserve_pct/100] if reserve_pct > 0 else [1, 0.01])

        with col_a:
            st.markdown(f"""
            <div style="background: linear-gradient(90deg, #00FF94, #00CC75); padding: 20px; border-radius: 10px; text-align: center;">
                <h3 style="margin:0; color: white;">Trading: {trading_pct:.1f}%</h3>
                <p style="margin:0; color: white; opacity: 0.9;">${trading_capital:,.2f}</p>
            </div>
            """, unsafe_allow_html=True)

        with col_b:
            if reserve_pct > 0:
                st.markdown(f"""
                <div style="background: linear-gradient(90deg, #4A90E2, #357ABD); padding: 20px; border-radius: 10px; text-align: center;">
                    <h3 style="margin:0; color: white;">Reserved: {reserve_pct:.1f}%</h3>
                    <p style="margin:0; color: white; opacity: 0.9;">${profit_reserve:,.2f}</p>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("No capital allocated yet.")

    st.markdown("---")

    # === AUTO-TRANSFER SETTINGS ===
    st.markdown("### ⚙️ Auto Profit Transfer")
    st.caption("Automatically move profits to reserve after each winning trade")

    with st.container(border=True):
        col1, col2 = st.columns(2)

        with col1:
            auto_enabled = st.checkbox(
                "Enable Auto-Transfer",
                value=allocation.get('auto_transfer_enabled', False),
                help="Automatically transfer a percentage of profits to reserve after winning trades"
            )

        with col2:
            if auto_enabled:
                st.success("✅ Auto-Transfer Active")
            else:
                st.info("⏸️ Auto-Transfer Disabled")

        if auto_enabled:
            ac1, ac2 = st.columns(2)

            with ac1:
                threshold = st.number_input(
                    "Min Profit to Transfer ($)",
                    min_value=1.0,
                    max_value=10000.0,
                    value=float(allocation.get('transfer_threshold', 100.0)),
                    step=10.0,
                    help="Only transfer if profit is above this amount"
                )

            with ac2:
                percentage = st.slider(
                    "% of Profit to Transfer",
                    min_value=10,
                    max_value=100,
                    value=int(allocation.get('transfer_percentage', 50)),
                    step=10,
                    help="How much of each winning trade's profit to move to reserve"
                )

            if st.button("💾 Save Auto-Transfer Settings", use_container_width=True):
                success = update_settings(
                    mode=current_mode,
                    auto_enabled=auto_enabled,
                    threshold=threshold,
                    percentage=percentage
                )
                if success:
                    st.success("✅ Settings saved!")
                    st.rerun()
                else:
                    st.error("❌ Failed to save settings")

        else:
            if st.button("💾 Save Settings (Disabled)", use_container_width=True):
                success = update_settings(mode=current_mode, auto_enabled=False)
                if success:
                    st.success("✅ Auto-transfer disabled")
                    st.rerun()

    st.markdown("---")

    # === MANUAL TRANSFERS ===
    st.markdown("### 🔄 Manual Transfer")
    st.caption("Move funds between trading capital and profit reserve")

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("#### ➡️ Protect Profits")
            st.caption("Move funds from trading to reserve")

            reserve_amount = st.number_input(
                "Amount to Protect ($)",
                min_value=0.0,
                max_value=float(trading_capital),
                value=0.0,
                step=50.0,
                key="reserve_amt"
            )

            if st.button("🏦 Transfer to Reserve", disabled=reserve_amount <= 0, use_container_width=True):
                success = manual_transfer(
                    mode=current_mode,
                    amount=reserve_amount,
                    direction='to_reserve'
                )
                if success:
                    st.success(f"✅ Protected ${reserve_amount:.2f}!")
                    st.rerun()
                else:
                    st.error("❌ Transfer failed")

    with col2:
        with st.container(border=True):
            st.markdown("#### ⬅️ Add Trading Capital")
            st.caption("Move funds from reserve to trading")

            trading_amount = st.number_input(
                "Amount to Add ($)",
                min_value=0.0,
                max_value=float(profit_reserve),
                value=0.0,
                step=50.0,
                key="trading_amt"
            )

            if st.button("🎯 Transfer to Trading", disabled=trading_amount <= 0, use_container_width=True):
                success = manual_transfer(
                    mode=current_mode,
                    amount=trading_amount,
                    direction='to_trading'
                )
                if success:
                    st.success(f"✅ Added ${trading_amount:.2f} to trading capital!")
                    st.rerun()
                else:
                    st.error("❌ Transfer failed")

    st.markdown("---")

    # === HOW IT WORKS ===
    with st.expander("ℹ️ How Capital Protection Works", expanded=False):
        st.markdown("""
        ### Virtual Wallet Separation

        This feature creates a **virtual separation** of your funds without requiring actual Binance sub-accounts or transfers.

        #### 🎯 Trading Capital
        - Amount the bot is **allowed** to use for trading
        - Limits risk exposure
        - Bot only places orders with this amount

        #### 🏦 Profit Reserve
        - **Protected** from trading losses
        - Accumulated profits moved here
        - Cannot be used by bot for new trades

        #### ⚙️ Auto-Transfer
        - After each **winning trade**, automatically moves a % of profit to reserve
        - Only triggers if profit ≥ threshold
        - Protects gains from future losses

        #### Example Flow:
        1. Start with $1,000 trading capital
        2. Bot makes $200 profit on a trade
        3. Auto-transfer (50%) moves $100 to reserve
        4. New trading capital: $1,100
        5. New profit reserve: $100 (protected)

        #### Benefits:
        - **Prevent capital loss**: Original investment protected
        - **Lock in gains**: Profits secured after each win
        - **Risk management**: Limit bot's exposure
        - **Psychological safety**: Know your profits are safe
        """)

    # === TRACKING INFO ===
    st.markdown("---")
    st.markdown("#### 📈 Tracking")

    t1, t2, t3 = st.columns(3)
    t1.metric("Total Deposited", f"${float(allocation.get('total_deposited', 0)):,.2f}")
    t2.metric("Total Withdrawn", f"${float(allocation.get('total_withdrawn', 0)):,.2f}")

    net = float(allocation.get('total_deposited', 0)) - float(allocation.get('total_withdrawn', 0))
    t3.metric("Net Flow", f"${net:,.2f}", delta=None if net == 0 else ("+In" if net > 0 else "-Out"))
