"""
Session Manager - Tracks trading sessions with comprehensive performance metrics
"""

import json
from datetime import datetime
from src.database import get_db

def create_session(mode='PAPER', start_balance=1000.0, session_name=None):
    """
    Create a new trading session.

    Args:
        mode: 'PAPER' or 'LIVE'
        start_balance: Starting capital
        session_name: Optional custom name (auto-generated if None)

    Returns:
        Session ID (UUID string)
    """
    db = get_db()

    # Generate session name if not provided
    if not session_name:
        count = get_session_count(mode) + 1
        prefix = "Paper Run" if mode == 'PAPER' else "Live Session"
        session_name = f"{prefix} #{count}"

    # Snapshot current bot_config
    config_snapshot = get_config_snapshot()

    try:
        result = db.table("trading_sessions").insert({
            "session_name": session_name,
            "mode": mode,
            "start_balance": start_balance,
            "current_balance": start_balance,
            "is_active": True,
            "config_snapshot": config_snapshot
        }).execute()

        session_id = result.data[0]['id']
        print(f"✅ Created session: {session_name} (ID: {session_id})")
        return session_id
    except Exception as e:
        print(f"❌ Failed to create session: {e}")
        return None


def get_active_session(mode='PAPER'):
    """
    Get the currently active session for the given mode.

    Returns:
        Session dict or None
    """
    db = get_db()
    try:
        result = db.table("trading_sessions")\
            .select("*")\
            .eq("mode", mode)\
            .eq("is_active", True)\
            .execute()

        return result.data[0] if result.data else None
    except Exception as e:
        print(f"⚠️ Error getting active session: {e}")
        return None


def end_session(session_id):
    """
    End a trading session.

    Args:
        session_id: UUID of session to end
    """
    db = get_db()
    try:
        db.table("trading_sessions").update({
            "ended_at": datetime.utcnow().isoformat(),
            "is_active": False
        }).eq("id", session_id).execute()

        print(f"✅ Ended session: {session_id}")
    except Exception as e:
        print(f"❌ Failed to end session: {e}")


def update_session_stats(session_id, trade_pnl):
    """
    Update session statistics after a trade closes.

    Args:
        session_id: UUID of session
        trade_pnl: P&L of the closed trade (positive for profit, negative for loss)
    """
    db = get_db()
    try:
        # Get current session
        session = db.table("trading_sessions").select("*").eq("id", session_id).execute()
        if not session.data:
            print(f"⚠️ Session {session_id} not found")
            return

        s = session.data[0]

        # Update counts
        total_trades = s['total_trades'] + 1
        winning_trades = s['winning_trades']
        losing_trades = s['losing_trades']
        gross_profit = s['gross_profit']
        gross_loss = s['gross_loss']

        if trade_pnl > 0:
            winning_trades += 1
            gross_profit += trade_pnl
            largest_win = max(s['largest_win'], trade_pnl)
        else:
            losing_trades += 1
            gross_loss += abs(trade_pnl)
            largest_loss = max(s['largest_loss'], abs(trade_pnl))

        net_pnl = s['net_pnl'] + trade_pnl
        current_balance = s['start_balance'] + net_pnl

        # Calculate derived metrics
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        avg_win = (gross_profit / winning_trades) if winning_trades > 0 else 0
        avg_loss = (gross_loss / losing_trades) if losing_trades > 0 else 0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.9 if gross_profit > 0 else 0)

        # Update session
        updates = {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "net_pnl": net_pnl,
            "current_balance": current_balance,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "updated_at": datetime.utcnow().isoformat()
        }

        if trade_pnl > 0:
            updates["largest_win"] = largest_win
        else:
            updates["largest_loss"] = largest_loss

        db.table("trading_sessions").update(updates).eq("id", session_id).execute()

        print(f"📊 Session stats updated | Trades: {total_trades} | Win Rate: {win_rate:.1f}% | Net P&L: ${net_pnl:.2f}")

    except Exception as e:
        print(f"❌ Failed to update session stats: {e}")


def take_balance_snapshot(session_id, balance, unrealized_pnl=0):
    """
    Take a periodic balance snapshot for drawdown tracking.

    Args:
        session_id: UUID of session
        balance: Current balance
        unrealized_pnl: Unrealized P&L from open positions
    """
    db = get_db()
    try:
        equity = balance + unrealized_pnl

        # Get peak equity for this session
        snapshots = db.table("balance_snapshots")\
            .select("peak_equity")\
            .eq("session_id", session_id)\
            .order("snapshot_at", desc=True)\
            .limit(1)\
            .execute()

        peak_equity = snapshots.data[0]['peak_equity'] if snapshots.data else equity
        peak_equity = max(peak_equity, equity)

        # Calculate drawdown
        drawdown = peak_equity - equity
        drawdown_pct = (drawdown / peak_equity * 100) if peak_equity > 0 else 0

        # Insert snapshot
        db.table("balance_snapshots").insert({
            "session_id": session_id,
            "balance": balance,
            "equity": equity,
            "peak_equity": peak_equity,
            "drawdown": drawdown,
            "drawdown_pct": drawdown_pct
        }).execute()

        # Update max drawdown in session if needed
        session = db.table("trading_sessions").select("max_drawdown, max_drawdown_pct").eq("id", session_id).execute()
        if session.data:
            s = session.data[0]
            if drawdown_pct > s['max_drawdown_pct']:
                db.table("trading_sessions").update({
                    "max_drawdown": drawdown,
                    "max_drawdown_pct": drawdown_pct
                }).eq("id", session_id).execute()

    except Exception as e:
        print(f"⚠️ Failed to take balance snapshot: {e}")


def log_config_change(session_id, key, old_value, new_value):
    """
    Log a configuration change during a session.

    Args:
        session_id: UUID of session
        key: Config key that changed
        old_value: Previous value
        new_value: New value
    """
    db = get_db()
    try:
        db.table("config_change_log").insert({
            "session_id": session_id,
            "key": key,
            "old_value": str(old_value),
            "new_value": str(new_value)
        }).execute()

        print(f"📝 Logged config change: {key} = {new_value} (was {old_value})")
    except Exception as e:
        print(f"⚠️ Failed to log config change: {e}")


def get_session_count(mode='PAPER'):
    """Get total number of sessions for a mode"""
    db = get_db()
    try:
        result = db.table("trading_sessions").select("id").eq("mode", mode).execute()
        return len(result.data) if result.data else 0
    except:
        return 0


def get_config_snapshot():
    """Snapshot all bot_config as JSON"""
    db = get_db()
    try:
        result = db.table("bot_config").select("key, value").execute()
        return {item['key']: item['value'] for item in result.data}
    except Exception as e:
        print(f"⚠️ Failed to snapshot config: {e}")
        return {}


def reset_simulation_session(new_balance=1000.0, session_name=None):
    """
    Reset paper trading: end current session, create new one, reset simulation_portfolio.

    Args:
        new_balance: Starting balance for new session
        session_name: Optional session name

    Returns:
        New session ID
    """
    db = get_db()

    # 1. End current paper session
    current = get_active_session(mode='PAPER')
    if current:
        end_session(current['id'])

    # 2. Create new session
    new_session_id = create_session(
        mode='PAPER',
        start_balance=new_balance,
        session_name=session_name
    )

    # 3. Reset simulation_portfolio
    try:
        db.table("simulation_portfolio").update({
            "balance": new_balance,
            "total_pnl": 0
        }).eq("id", 1).execute()

        print(f"✅ Reset simulation portfolio to ${new_balance:,.2f}")
    except Exception as e:
        print(f"❌ Failed to reset simulation portfolio: {e}")

    return new_session_id
