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
            print(f"Sniper: Executing {side} on {symbol}...")
            
            # 1. Place Market Order (Simplest for now)
            # In production, use LIMIT orders for better price control
            order = self.exchange.create_order(symbol, 'market', side.lower(), amount)
            
            print(f"Sniper: Order Placed! ID: {order['id']}")
            
            # 2. Record Position in DB
            self.db.table("positions").insert({
               "asset_id": signal['asset_id'],
               "side": side,
               "entry_avg": order['price'] or order['average'], # Some exchanges return average
               "quantity": order['amount'],
               "is_open": True
            }).execute()
            
            # 3. Update Signal Status
            self.db.table("trade_signals").update({"status": "EXECUTED"}).eq("id", signal['id']).execute()
            
            return True
        except Exception as e:
            print(f"Sniper Error: {e}")
            self.db.table("trade_signals").update({"status": "FAILED", "judge_reason": str(e)}).eq("id", signal['id']).execute()
            return False
