class HeadHunter:
    """
    THE HEAD HUNTER (Screener)
    Role: Filters stocks/crypto by fundamentals (ROE, PEG, etc.)
    Status: Placeholder for future implementation.
    """
    def __init__(self, db_client=None):
        self.db = db_client
        # Default Config
        self.min_volume = 10000000 # 10M USDT default
        self.universe = "ALL" # ALL, SAFE_LIST, TOP_30

    def load_config(self):
        """Reloads constraints from DB"""
        if not self.db: return
        try:
            cfg = self.db.table("bot_config").select("*").execute()
            cfg_dict = {row['key']: row['value'] for row in cfg.data}
            self.min_volume = float(cfg_dict.get("MIN_VOLUME", 10000000))
            self.universe = cfg_dict.get("TRADING_UNIVERSE", "ALL").replace('"', '')
        except Exception as e:
            print(f"HeadHunter Config Error: {e}")

    def screen_market(self, candidates):
        """
        Filters the list of candidates based on:
        1. Liquidity (Min Volume)
        2. Status (Whitelist/Blacklist)
        3. Universe Mode
        """
        self.load_config()
        
        # 1. Fetch Fundamental Data
        f_data = {}
        try:
            if self.db:
                rows = self.db.table("fundamental_coins").select("*").execute()
                f_data = {r['symbol']: r['status'] for r in rows.data}
        except: pass

        qualified = []
        
        print(f"🕵️ Head Hunter: Screening {len(candidates)} candidates...")
        print(f"   (Mode: {self.universe}, Min Vol: ${self.min_volume:,.0f})")

        for coin in candidates:
            symbol = coin['symbol']
            vol = coin.get('volume', 0) # Key from Spy is 'volume'
            status = f_data.get(symbol, 'NEUTRAL')
            
            # A. Blacklist Check
            if status == 'BLACKLIST':
                print(f"   ❌ {symbol}: Blacklisted")
                continue
                
            # B. Volume Check
            if vol < self.min_volume:
                # Exception: Whitelisted coins can bypass volume check? Maybe not.
                # Let's say Whitelisted coins MUST still have volume, but maybe lower?
                # For now, strict volume check.
                if status != 'WHITELIST': # Whitelist bypasses volume?? No, risky.
                     # Let's just log it.
                     pass
                if vol < self.min_volume:
                    # print(f"   ⚠️ {symbol}: Low Vol (${vol:,.0f})") # Too noisy
                    continue

            # C. Universe Check
            if self.universe == "SAFE_LIST" and status != 'WHITELIST':
                continue
            
            qualified.append(coin)
            
        print(f"✅ Head Hunter: Passed {len(qualified)}/{len(candidates)} candidates.")
        return qualified
