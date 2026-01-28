"""
Capital Manager - Virtual wallet separation for capital protection
Separates trading capital from profit reserve to prevent capital loss
"""

from src.database import get_db

def get_allocation(mode='PAPER'):
    """
    Get capital allocation for the given mode.

    Args:
        mode: 'PAPER' or 'LIVE'

    Returns:
        Dict with allocation data or None
    """
    db = get_db()
    try:
        result = db.table("capital_allocation").select("*").eq("mode", mode).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"⚠️ Failed to get capital allocation: {e}")
        return None


def get_available_trading_balance(mode='PAPER', actual_balance=0.0):
    """
    Get the balance available for trading (respects trading_capital limit).
    Bot can only trade with trading_capital, not profit_reserve.

    Args:
        mode: 'PAPER' or 'LIVE'
        actual_balance: Real wallet balance from Binance/simulation

    Returns:
        Available trading balance (minimum of actual_balance and trading_capital)
    """
    allocation = get_allocation(mode)
    if not allocation:
        # If no allocation record, return actual balance (backward compatibility)
        return actual_balance

    trading_capital = float(allocation['trading_capital'])

    # Bot can only use the smaller of:
    # 1. Actual wallet balance
    # 2. User-defined trading capital limit
    available = min(actual_balance, trading_capital)

    return available


def auto_transfer_profit(mode='PAPER', profit_amount=0.0):
    """
    Automatically transfer a percentage of profit to reserve if settings allow.
    Called after a winning trade closes.

    Args:
        mode: 'PAPER' or 'LIVE'
        profit_amount: Profit from the trade (positive value)

    Returns:
        Transferred amount or 0
    """
    if profit_amount <= 0:
        return 0.0

    db = get_db()
    allocation = get_allocation(mode)

    if not allocation:
        print(f"⚠️ No capital allocation found for {mode}")
        return 0.0

    # Check if auto-transfer is enabled
    if not allocation.get('auto_transfer_enabled', False):
        return 0.0

    # Check if profit meets threshold
    threshold = float(allocation.get('transfer_threshold', 100.0))
    if profit_amount < threshold:
        print(f"[Capital] Profit ${profit_amount:.2f} below threshold ${threshold:.2f}, skipping auto-transfer")
        return 0.0

    # Calculate transfer amount
    transfer_pct = float(allocation.get('transfer_percentage', 50.0)) / 100.0
    transfer_amount = profit_amount * transfer_pct

    # Update allocation
    try:
        new_trading_capital = float(allocation['trading_capital']) - transfer_amount
        new_profit_reserve = float(allocation['profit_reserve']) + transfer_amount

        # Prevent negative trading capital
        if new_trading_capital < 0:
            print(f"⚠️ Cannot transfer ${transfer_amount:.2f}, would make trading_capital negative")
            return 0.0

        db.table("capital_allocation").update({
            "trading_capital": new_trading_capital,
            "profit_reserve": new_profit_reserve
        }).eq("mode", mode).execute()

        print(f"💰 Auto-transferred ${transfer_amount:.2f} to profit reserve ({transfer_pct*100:.0f}% of ${profit_amount:.2f})")
        print(f"   New Trading Capital: ${new_trading_capital:.2f} | Profit Reserve: ${new_profit_reserve:.2f}")

        return transfer_amount

    except Exception as e:
        print(f"❌ Auto-transfer failed: {e}")
        return 0.0


def manual_transfer(mode='PAPER', amount=0.0, direction='to_reserve'):
    """
    Manually transfer funds between trading capital and profit reserve.

    Args:
        mode: 'PAPER' or 'LIVE'
        amount: Amount to transfer (positive value)
        direction: 'to_reserve' or 'to_trading'

    Returns:
        Success boolean
    """
    if amount <= 0:
        print("⚠️ Transfer amount must be positive")
        return False

    db = get_db()
    allocation = get_allocation(mode)

    if not allocation:
        print(f"⚠️ No capital allocation found for {mode}")
        return False

    try:
        trading_capital = float(allocation['trading_capital'])
        profit_reserve = float(allocation['profit_reserve'])

        if direction == 'to_reserve':
            # Move from trading to reserve
            if trading_capital < amount:
                print(f"⚠️ Insufficient trading capital: ${trading_capital:.2f} < ${amount:.2f}")
                return False

            new_trading = trading_capital - amount
            new_reserve = profit_reserve + amount

            db.table("capital_allocation").update({
                "trading_capital": new_trading,
                "profit_reserve": new_reserve
            }).eq("mode", mode).execute()

            print(f"✅ Moved ${amount:.2f} to profit reserve")

        elif direction == 'to_trading':
            # Move from reserve to trading
            if profit_reserve < amount:
                print(f"⚠️ Insufficient profit reserve: ${profit_reserve:.2f} < ${amount:.2f}")
                return False

            new_trading = trading_capital + amount
            new_reserve = profit_reserve - amount

            db.table("capital_allocation").update({
                "trading_capital": new_trading,
                "profit_reserve": new_reserve,
                "total_deposited": float(allocation.get('total_deposited', 0)) + amount
            }).eq("mode", mode).execute()

            print(f"✅ Moved ${amount:.2f} to trading capital")

        else:
            print(f"⚠️ Invalid direction: {direction}")
            return False

        return True

    except Exception as e:
        print(f"❌ Manual transfer failed: {e}")
        return False


def initialize_allocation(mode='PAPER', initial_capital=1000.0):
    """
    Initialize capital allocation for a mode if it doesn't exist.

    Args:
        mode: 'PAPER' or 'LIVE'
        initial_capital: Starting trading capital
    """
    db = get_db()
    try:
        # Check if exists
        existing = get_allocation(mode)
        if existing:
            print(f"[Capital] Allocation for {mode} already exists")
            return

        # Create new allocation
        db.table("capital_allocation").insert({
            "mode": mode,
            "trading_capital": initial_capital,
            "profit_reserve": 0.0,
            "auto_transfer_enabled": False,
            "transfer_threshold": 100.0,
            "transfer_percentage": 50.0
        }).execute()

        print(f"✅ Initialized capital allocation for {mode} with ${initial_capital:.2f}")

    except Exception as e:
        print(f"⚠️ Failed to initialize allocation: {e}")


def update_settings(mode='PAPER', auto_enabled=None, threshold=None, percentage=None):
    """
    Update auto-transfer settings.

    Args:
        mode: 'PAPER' or 'LIVE'
        auto_enabled: Enable/disable auto-transfer (boolean)
        threshold: Minimum profit to trigger transfer (float)
        percentage: Percentage of profit to transfer (float 0-100)

    Returns:
        Success boolean
    """
    db = get_db()
    try:
        updates = {}

        if auto_enabled is not None:
            updates['auto_transfer_enabled'] = auto_enabled
        if threshold is not None:
            updates['transfer_threshold'] = float(threshold)
        if percentage is not None:
            updates['transfer_percentage'] = float(percentage)

        if not updates:
            return False

        db.table("capital_allocation").update(updates).eq("mode", mode).execute()
        print(f"✅ Updated capital settings for {mode}")
        return True

    except Exception as e:
        print(f"❌ Failed to update settings: {e}")
        return False
