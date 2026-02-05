import ccxt
import os
import threading
from datetime import datetime
from src.database import get_db
from src.roles.job_price import PriceSpy # Re-use Spy's connection logic if possible, or new instance
from src.session_manager import get_active_session, update_session_stats
from src.capital_manager import auto_transfer_profit

# Lock to prevent concurrent simulation balance updates
_sim_balance_lock = threading.Lock()

class SniperExecutor:
    """
    THE SNIPER (Execution Engine)
    Role: Executes BUY/SELL orders on the exchange based on signals approved by The Judge.
    """
    def __init__(self, spy_instance: PriceSpy = None):
        # Reuse existing PriceSpy to avoid duplicate CCXT connections and rate limit issues
        self.spy = spy_instance or PriceSpy()
        self.exchange = self.spy.exchange
        self.db = get_db()

    def execute_order(self, signal):
        """
        Executes an order.
        :param signal: Dict containing {symbol, side, amount, etc.}
        """
        symbol = signal['assets']['symbol']
        side = signal['signal_type'] # BUY or SELL
        amount = signal.get('order_size', signal['entry_target'])  # USDT amount from Judge
        
        # SAFETY CHECK: Double check with DB if signal is APPROVED
        # (Already filtered before calling this, but good practice)
        
        try:
            # CHECK TRADING MODE
            try:
                conf = self.db.table("bot_config").select("*").eq("key", "TRADING_MODE").execute()
                mode = conf.data[0]['value'] if conf.data else "PAPER"
                # CRITICAL: Strip literal quotes if present (Supabase JSON/String quirk)
                mode = str(mode).replace('"', '').strip()
            except Exception as e:
                print(f"Sniper: Mode fetch error: {e}")
                mode = "PAPER"

            is_sim = (mode == 'PAPER')
            print(f"Sniper: Executing {side} on {symbol} (Mode: {mode})...")
            
            # Ensure markets are loaded (Required for cost_to_precision)
            if not self.exchange.markets:
                print("Sniper: Markets not loaded, fetching now...")
                self.spy.load_markets_custom()
            
            fill_price = 0
            fill_amount = amount

            if is_sim:
                # -- SIMULATION MODE --
                # Fetch real price for accurate simulation
                ticker = self.exchange.fetch_ticker(symbol)
                fill_price = ticker['last']

                # Use lock to prevent concurrent balance corruption
                with _sim_balance_lock:
                    # Fetch mock wallet
                    wallet_res = self.db.table("simulation_portfolio").select("*").eq("id", 1).execute()
                    if not wallet_res.data:
                        # Initialize if missing
                        self.db.table("simulation_portfolio").insert({"id": 1, "balance": 1000.0}).execute()
                        current_bal = 1000.0
                    else:
                        current_bal = float(wallet_res.data[0]['balance'])

                    if side.upper() == 'BUY':
                        # 'amount' is in USDT (from Judge)
                        cost = amount
                        if current_bal < cost:
                            raise Exception(f"Insufficient Simulation Balance: {current_bal:,.2f} < {cost:,.2f} USDT")

                        new_bal = current_bal - cost
                        self.db.table("simulation_portfolio").update({"balance": new_bal}).eq("id", 1).execute()

                        fill_amount = cost / fill_price # Qty in asset
                        print(f"Sniper (Sim): BUY {fill_amount:.6f} {symbol} at ${fill_price:,.2f}")

                    elif side.upper() == 'SELL':
                        # Find any open simulation position for this asset to close
                        pos_res = self.db.table("positions").select("*")\
                            .eq("asset_id", signal['asset_id'])\
                            .eq("is_open", True)\
                            .eq("is_sim", True)\
                            .order("created_at", desc=True).limit(1).execute()

                        if pos_res.data:
                            pos = pos_res.data[0]
                            qty = float(pos['quantity'])
                            entry_price = float(pos['entry_avg'])
                            revenue = qty * fill_price
                            pnl = revenue - (qty * entry_price)

                            new_bal = current_bal + revenue
                            self.db.table("simulation_portfolio").update({"balance": new_bal}).eq("id", 1).execute()

                            # Extract Exit Reason (Default: AI_SELL_SIGNAL)
                            exit_reason = signal.get('exit_reason', 'AI_SELL_SIGNAL')

                            # Close the existing position with exit data
                            self.db.table("positions").update({
                                "is_open": False,
                                "exit_price": fill_price,
                                "pnl": pnl,
                                "exit_reason": exit_reason,
                                "closed_at": datetime.utcnow().isoformat()
                            }).eq("id", pos['id']).execute()

                            # Update session stats
                            session_id = pos.get('session_id')
                            if session_id:
                                update_session_stats(session_id, pnl)

                            # Auto-transfer profit if enabled (only for winning trades)
                            if pnl > 0:
                                mode = 'PAPER' if is_sim else 'LIVE'
                                transferred = auto_transfer_profit(mode=mode, profit_amount=pnl)
                                if transferred > 0:
                                    # Update simulation balance to reflect transfer
                                    new_bal_after_transfer = current_bal + revenue - transferred
                                    self.db.table("simulation_portfolio").update({"balance": new_bal_after_transfer}).eq("id", 1).execute()

                            fill_amount = qty
                            print(f"Sniper (Sim): SELL {qty:.6f} {symbol} at ${fill_price:,.2f}. Reason: {exit_reason} | PnL: ${pnl:,.2f}")
                        else:
                            raise Exception(f"No open simulation position found for {symbol} to sell.")
                
            else:
                # -- LIVE MODE --
                # 1. Place Market Order
                if side.upper() == 'BUY':
                    print(f"Sniper: Placing Market BUY for {amount} USDT...")
                    # Convert quote amount (USDT) -> base amount using current price
                    ticker = self.exchange.fetch_ticker(symbol)
                    last_price = ticker.get('last') or ticker.get('close')
                    if not last_price or float(last_price) <= 0:
                        raise Exception(f"Cannot determine market price for {symbol} to size BUY")
                    base_amount = float(amount) / float(last_price)
                    if hasattr(self.exchange, 'amount_to_precision'):
                        base_amount = float(self.exchange.amount_to_precision(symbol, base_amount))
                    order = self.exchange.create_order(symbol, 'market', 'buy', base_amount, None, {
                        'type': 'spot'
                    })
                elif side.upper() == 'SELL':
                    # For SELL: Look up the open position to get base quantity
                    pos_res = self.db.table("positions").select("*")\
                        .eq("asset_id", signal['asset_id'])\
                        .eq("is_open", True)\
                        .eq("is_sim", False)\
                        .order("created_at", desc=True).limit(1).execute()

                    if not pos_res.data:
                        raise Exception(f"No open LIVE position found for {symbol} to sell.")

                    sell_qty = float(pos_res.data[0]['quantity'])
                    print(f"Sniper: Placing Market SELL for {sell_qty} qty of {symbol}...")
                    order = self.exchange.create_order(symbol, 'market', 'sell', sell_qty, None, {
                        'type': 'spot'
                    })
                else:
                    raise Exception(f"Invalid Signal Type: {side}")

                # Extract fill price from order response (Binance market orders may return price=None)
                fill_price = order.get('average') or order.get('price') or 0
                if not fill_price or float(fill_price) == 0:
                    # Fallback: fetch current market price if order response missing price
                    try:
                        fallback_ticker = self.exchange.fetch_ticker(symbol)
                        fill_price = fallback_ticker['last']
                        print(f"Sniper: Order price missing from response, using market price: ${fill_price:,.2f}")
                    except Exception:
                        raise Exception(f"Cannot determine fill price for {symbol} - order response and ticker both failed")
                fill_price = float(fill_price)
                fill_amount = float(order.get('amount', amount))
                print(f"Sniper: Order Placed! ID: {order['id']} @ ${fill_price:,.2f}")
            
            # 2. Record Position / History in DB
            if side.upper() == 'BUY':
                # BUY: Create a new open position
                # Map BUY→LONG to match DB CHECK constraint (side IN ('LONG','SHORT'))
                entry_atr = signal.get('entry_atr', 0.0)  # Get ATR from signal

                # Get active session for current mode
                mode = 'PAPER' if is_sim else 'LIVE'
                session = get_active_session(mode=mode)
                session_id = session['id'] if session else None

                self.db.table("positions").insert({
                   "asset_id": signal['asset_id'],
                   "side": "LONG",
                   "entry_avg": fill_price,
                   "quantity": fill_amount,
                   "is_open": True,
                   "is_sim": is_sim,
                   "highest_price_seen": fill_price,
                   "trailing_stop_price": None,
                   "entry_atr": entry_atr,  # Store ATR for trailing stop
                   "session_id": session_id  # Link to trading session
                }).execute()
            else:
                # SELL: Position already closed above (sim) or record close for live
                if not is_sim:
                    # For LIVE mode, close the position that was looked up earlier for the sell order
                    # (pos_res was already fetched at line 126-130 before placing the order)
                    if pos_res and pos_res.data:
                        pos = pos_res.data[0]
                        entry_price = float(pos['entry_avg'])
                        qty = float(pos['quantity'])
                        pnl = (fill_price - entry_price) * qty
                        
                        # Extract Exit Reason (Default: AI_SELL_SIGNAL)
                        exit_reason = signal.get('exit_reason', 'AI_SELL_SIGNAL')
                        
                        self.db.table("positions").update({
                            "is_open": False,
                            "exit_price": fill_price,
                            "pnl": pnl,
                            "exit_reason": exit_reason,
                            "closed_at": datetime.utcnow().isoformat()
                        }).eq("id", pos['id']).execute()

                        # Update session stats
                        session_id = pos.get('session_id')
                        if session_id:
                            update_session_stats(session_id, pnl)

                        # Auto-transfer profit if enabled (only for winning trades)
                        if pnl > 0:
                            mode = 'LIVE'
                            auto_transfer_profit(mode=mode, profit_amount=pnl)

                        print(f"Sniper (Live): Closed position. Exit: ${fill_price:,.2f} | Reason: {exit_reason} | PnL: ${pnl:,.2f}")
            
            # 3. Update Signal Status
            self.db.table("trade_signals").update({"status": "EXECUTED", "is_sim": is_sim}).eq("id", signal['id']).execute()
            
            return True
        except Exception as e:
            print(f"Sniper Error: {e}")
            self.db.table("trade_signals").update({"status": "FAILED", "judge_reason": str(e)}).eq("id", signal['id']).execute()
            return False
