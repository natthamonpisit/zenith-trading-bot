import ccxt
import os
from src.database import get_db
from src.roles.job_price import PriceSpy # Re-use Spy's connection logic if possible, or new instance

class SniperExecutor:
    """
    THE SNIPER (Execution Engine)
    Role: Executes BUY/SELL orders on the exchange based on signals approved by The Judge.
    """
    def __init__(self):
        # We can actually reuse the Spy's exchange connection to avoid code duplication
        # But for separation of concerns, let's init a new one or pass it in.
        # For simplicity, let's create a new instance using the same robust logic as Spy
        self.spy = PriceSpy() 
        self.exchange = self.spy.exchange
        self.db = get_db()

    def execute_order(self, signal):
        """
        Executes an order.
        :param signal: Dict containing {symbol, side, amount, etc.}
        """
        symbol = signal['assets']['symbol']
        side = signal['signal_type'] # BUY or SELL
        amount = signal['entry_target'] # reusing field for amount for now, or calc size
        
        # SAFETY CHECK: Double check with DB if signal is APPROVED
        # (Already filtered before calling this, but good practice)
        
        try:
            # CHECK TRADING MODE
            try:
                conf = self.db.table("bot_config").select("*").eq("key", "TRADING_MODE").execute()
                mode = conf.data[0]['value'] if conf.data else "PAPER"
                # CRITICAL: Strip literal quotes if present (Supabase JSON/String quirk)
                mode = str(mode).replace('"', '').strip()
            except: mode = "PAPER"

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
                        revenue = qty * fill_price
                        
                        new_bal = current_bal + revenue
                        self.db.table("simulation_portfolio").update({"balance": new_bal}).eq("id", 1).execute()
                        
                        # Close the existing position
                        self.db.table("positions").update({"is_open": False}).eq("id", pos['id']).execute()
                        
                        fill_amount = qty
                        print(f"Sniper (Sim): SELL {qty:.6f} {symbol} at ${fill_price:,.2f}. Revenue: ${revenue:,.2f}")
                    else:
                        raise Exception(f"No open simulation position found for {symbol} to sell.")
                
            else:
                # -- LIVE MODE --
                # 1. Place Market Order
                # For Binance/Binance TH: Use quoteOrderQty for BUY to spend USDT amount
                if side.upper() == 'BUY':
                    print(f"Sniper: Placing Market BUY for {amount} USDT...")
                    order = self.exchange.create_order(symbol, 'market', 'buy', amount, None, {
                        'quoteOrderQty': self.exchange.cost_to_precision(symbol, amount),
                        'type': 'spot'
                    })
                else:
                    # For SELL: 'amount' is in base currency (like 0.001 BTC)
                    print(f"Sniper: Placing Market SELL for {amount} qty...")
                    order = self.exchange.create_order(symbol, 'market', 'sell', amount, None, {
                        'type': 'spot'
                    })
                
                fill_price = order.get('price') or order.get('average', 0)
                fill_amount = order.get('amount', amount)
                print(f"Sniper: Order Placed! ID: {order['id']}")
            
            # Guard: If we reached here without BUY/SELL logic triggering above (e.g. unknown side), raise error
            if side.upper() not in ['BUY', 'SELL']:
                raise Exception(f"Invalid Signal Type: {side}")

            # 2. Record Position / History in DB
            # For BUY, we ALWAYS create a new open position
            # For SELL (Sim), we already closed the position above, but we might want to record the "Sell" action too.
            # To keep history simple, let's insert the action normally.
            self.db.table("positions").insert({
               "asset_id": signal['asset_id'],
               "side": side,
               "entry_avg": fill_price,
               "quantity": fill_amount,
               "is_open": True if side.upper() == 'BUY' else False,
               "is_sim": is_sim
            }).execute()
            
            # 3. Update Signal Status
            self.db.table("trade_signals").update({"status": "EXECUTED", "is_sim": is_sim}).eq("id", signal['id']).execute()
            
            return True
        except Exception as e:
            print(f"Sniper Error: {e}")
            self.db.table("trade_signals").update({"status": "FAILED", "judge_reason": str(e)}).eq("id", signal['id']).execute()
            return False

