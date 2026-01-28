"""
Wallet Sync Role - Fetches Binance wallet balance and syncs to database

This role runs periodically on Railway bot to fetch wallet balance
and store it in Supabase, allowing Streamlit dashboard to display
wallet data without direct Binance API access.
"""


class WalletSync:
    """
    Syncs Binance wallet balance to database every 5 minutes
    
    Attributes:
        db: Supabase database client
        exchange: CCXT exchange instance (Binance)
    """
    
    def __init__(self, db, exchange):
        """
        Initialize WalletSync role
        
        Args:
            db: Supabase database client
            exchange: CCXT exchange instance
        """
        self.db = db
        self.exchange = exchange
        print("💰 WalletSync initialized")
        try:
            self.db.table("system_logs").insert({
                "role": "WalletSync",
                "message": "💰 WalletSync initialized",
                "level": "INFO"
            }).execute()
        except:
            pass
    
    def sync_wallet(self):
        """
        Fetch wallet balance from Binance and update database
        
        Process:
        1. Fetch balance from Binance API
        2. Clear old wallet data from database
        3. Insert fresh balance data
        4. Log results
        
        Returns:
            bool: True if sync successful, False otherwise
        """
        try:
            print("🔄 Fetching wallet balance from Binance...")
            
            # Fetch balance from Binance
            balance = self.exchange.fetch_balance()
            
            # Prepare asset list (only non-zero balances)
            assets = []
            for asset, amount in balance['total'].items():
                if amount > 0:  # Only active balances
                    # Calculate USD value
                    usd_value = 0.0
                    if asset == 'USDT':
                        usd_value = amount
                    else:
                        try:
                            ticker = self.exchange.fetch_ticker(f"{asset}/USDT")
                            usd_value = amount * ticker['last']
                        except Exception as e:
                            print(f"⚠️ Could not fetch price for {asset}: {e}")
                            usd_value = 0.0
                    
                    assets.append({
                        "asset": asset,
                        "free": float(balance['free'].get(asset, 0)),
                        "locked": float(balance['used'].get(asset, 0)),
                        "total": float(amount),
                        "usd_value": float(usd_value),
                        "is_active": True
                    })
            
            if not assets:
                print("⚠️ No active wallet balances found")
                self.db.table("system_logs").insert({
                    "role": "WalletSync",
                    "message": "⚠️ No active wallet balances found",
                    "level": "WARNING"
                }).execute()
                return False
            
            # Clear old data (delete all existing records)
            try:
                self.db.table("wallet_balance").delete().neq("id", 0).execute()
            except Exception as e:
                print(f"⚠️ Failed to clear old wallet data: {e}")
            
            # Insert fresh data
            result = self.db.table("wallet_balance").insert(assets).execute()
            
            # Log success
            total_usdt = sum(a['total'] for a in assets if a['asset'] == 'USDT')
            msg = f"✅ Wallet synced: {len(assets)} assets, ${total_usdt:,.2f} USDT"
            print(msg)
            self.db.table("system_logs").insert({
                "role": "WalletSync",
                "message": msg,
                "level": "SUCCESS"
            }).execute()
            
            return True
            
        except Exception as e:
            msg = f"❌ Wallet sync failed: {e}"
            print(msg)
            self.db.table("system_logs").insert({
                "role": "WalletSync",
                "message": msg,
                "level": "ERROR"
            }).execute()
            return False
    
    def get_total_balance_usd(self):
        """
        Get total wallet balance in USD (approximate)
        
        Note: This is a simple estimate using USDT as proxy for USD
        For accurate USD value, would need to fetch current prices
        
        Returns:
            float: Approximate total balance in USD
        """
        try:
            result = self.db.table("wallet_balance")\
                .select("asset, total")\
                .eq("is_active", True)\
                .execute()
            
            if not result.data:
                return 0.0
            
            # Simple estimate: just return USDT amount
            # TODO: Convert other assets to USD using current prices
            total_usdt = sum(
                item['total'] for item in result.data 
                if item['asset'] == 'USDT'
            )
            
            return float(total_usdt)
            
        except Exception as e:
            print(f"❌ Failed to get total balance: {e}")
            return 0.0
