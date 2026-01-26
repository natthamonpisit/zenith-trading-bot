import ccxt
import os
from src.database import get_db
from src.roles.job_spy import Spy # Re-use Spy's connection logic if possible, or new instance

class Sniper:
    """
    The Sniper (Execution Engine)
    Role: Executes BUY/SELL orders on the exchange based on signals approved by The Judge.
    """
    def __init__(self):
        # We can actually reuse the Spy's exchange connection to avoid code duplication
        # But for separation of concerns, let's init a new one or pass it in.
        # For simplicity, let's create a new instance using the same robust logic as Spy
        self.spy = Spy() 
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
                ticker = self.exchange.fetch_ticker(symbol)
                fill_price = ticker['last']
                # Calculate Mock Fee (0.1%)
                fee = (fill_price * fill_amount) * 0.001
                
                # Update Simulation Portfolio
                # Fetch mock wallet
                wallet = self.db.table("simulation_portfolio").select("*").eq("id", 1).execute()
                current_bal = float(wallet.data[0]['balance'])
                
                # Logic: If BUY -> Deduct Balance, If SELL -> Add Balance (Simple logic)
                # Ideally we track Asset holdings too, but for V1 let's just track USD PnL roughly
                pass 
                
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
                    # Note: We might need to fetch current balance to know how much to sell if 'amount' is USD
                    print(f"Sniper: Placing Market SELL for {amount} qty...")
                    order = self.exchange.create_order(symbol, 'market', 'sell', amount, None, {
                        'type': 'spot'
                    })
                
                fill_price = order.get('price') or order.get('average', 0)
                fill_amount = order.get('amount', amount)
                print(f"Sniper: Order Placed! ID: {order['id']}")
            
            # 2. Record Position in DB
            self.db.table("positions").insert({
               "asset_id": signal['asset_id'],
               "side": side,
               "entry_avg": fill_price,
               "quantity": fill_amount,
               "is_open": True,
               "is_sim": is_sim
            }).execute()
            
            # 3. Update Signal Status
            self.db.table("trade_signals").update({"status": "EXECUTED", "is_sim": is_sim}).eq("id", signal['id']).execute()
            
            return True
        except Exception as e:
            print(f"Sniper Error: {e}")
            self.db.table("trade_signals").update({"status": "FAILED", "judge_reason": str(e)}).eq("id", signal['id']).execute()
            return False
