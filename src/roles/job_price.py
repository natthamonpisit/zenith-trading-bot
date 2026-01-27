import ccxt # Standard CCXT (Free Version)
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()

class PriceSpy:
    """
    THE SPY A (Price Collector)
    Role: Fetches market data (OHLCV) from the exchange and calculates basic technical indicators.
    """
    def __init__(self, exchange_id='binance'):
        self.api_key = os.environ.get("BINANCE_API_KEY")
        self.secret = os.environ.get("BINANCE_SECRET")
        self.api_url = os.environ.get("BINANCE_API_URL", "https://api.binance.com")
        
        # Initialize basic CCXT instance without loading markets yet
        options = {
            'defaultType': 'spot',
            'fetchCurrencies': False, 
            'fetchMarginPairs': False, 
            'fetchPositions': False,   
            'adjustForTimeDifference': True,
            'recvWindow': 10000,
            'warnOnFetchMarginPairs': False,
        } 
        
        # Override for Binance TH specific behavior
        if "binance.th" in self.api_url or "api.binance.th" in self.api_url:
             self.exchange = ccxt.binance({
                'apiKey': self.api_key,
                'secret': self.secret,
                'timeout': 10000, # Correct location
                'options': options,
             })
             # Override URLs map manually to point to TH
             self.exchange.urls['api'] = {
                'public': 'https://api.binance.th/api/v1',
                'private': 'https://api.binance.th/api/v1',
                'v3': 'https://api.binance.th/api/v1', 
                'v1': 'https://api.binance.th/api/v1',
                'sapi': 'https://api.binance.th/sapi/v1',
             }
             # Strictly disable all non-spot features to prevent 404 probes
             self.exchange.has['fetchMarginPairs'] = False
             self.exchange.has['fetchPositions'] = False
             self.exchange.has['fetchCurrencies'] = False
             self.exchange.has['fetchIsolatedMarginPairs'] = False
             self.exchange.has['fetchCrossMarginPairs'] = False
             self.exchange.has['margin'] = False
             self.exchange.has['swap'] = False
             self.exchange.has['future'] = False
        else:
             self.exchange = getattr(ccxt, exchange_id)({
                'apiKey': self.api_key,
                'secret': self.secret,
                'options': options
            })

    def load_markets_custom(self):
        """Lazy load markets specifically for Binance TH if needed"""
        if "binance.th" in self.api_url or "api.binance.th" in self.api_url:
            try:
                import requests
                print("Spy: Fetching markets from Binance TH (v1/exchangeInfo)...")
                response = requests.get('https://api.binance.th/api/v1/exchangeInfo', timeout=5)
                data = response.json()
                
                markets_map = {}
                for s in data['symbols']:
                    if s['status'] != 'TRADING': continue
                    
                    market_id = s['symbol']
                    base_id = s['baseAsset']
                    quote_id = s['quoteAsset']
                    symbol = f"{base_id}/{quote_id}"
                    
                    markets_map[symbol] = {
                        'id': market_id,
                        'symbol': symbol,
                        'base': base_id,
                        'quote': quote_id,
                        'baseId': base_id,
                        'quoteId': quote_id,
                        'active': True,
                        'type': 'spot',
                        'spot': True,
                        'info': s
                    }
                
                # Use set_markets to correctly initialize internal CCXT state
                self.exchange.set_markets(markets_map)
                print(f"Spy: Loaded {len(markets_map)} markets.")
            except Exception as e:
                print(f"Spy: Failed to dynamic load markets: {e}")
                # Fallback
                self.exchange.set_markets({'BTC/USDT': {'id': 'BTCUSDT', 'symbol': 'BTC/USDT', 'base': 'BTC', 'quote': 'USDT', 'active': True, 'type': 'spot', 'spot': True}})
        else:
            self.exchange.load_markets()


    def fetch_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 100):
        try:
            # Check market loading (Lazy Load)
            if not self.exchange.markets:
                self.load_markets_custom()
            
            # Fetch data
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            # Convert to DataFrame
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            return df
        except Exception as e:
            print(f"Spy (Data Fetch) Error: {e}")
            return None

    def get_usdt_thb_rate(self):
        """Fetches USDT/THB price for display"""
        try:
            # Try fetching from exchange if available, else approximate
            # Binance TH usually has USDT/THB
            ticker = self.exchange.fetch_ticker('USDT/THB')
            return float(ticker['last'])
        except:
            return 35.0  # Fallback constant

    def get_account_balance(self):
        """Fetches account balance securely"""
        try:
             # Force load if valid
             balance = self.exchange.fetch_balance({'type': 'spot'})
             return balance
        except Exception as e:
             print(f"Spy (Balance) Error: {e}")
             return None

    def get_top_symbols(self, limit=10):
        """Fetches top USDT pairs by 24h Volume (Robust Loop for Binance TH)"""
        try:
            if not self.exchange.markets:
                self.load_markets_custom()

            # Candidate List (Top 30 Popular Coins on Binance TH)
            candidates = [
                "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", 
                "DOGE/USDT", "ADA/USDT", "LINK/USDT", "DOT/USDT", "MATIC/USDT",
                "LTC/USDT", "TRX/USDT", "AVAX/USDT", "ONE/USDT", "FTM/USDT",
                "SAND/USDT", "GALA/USDT", "NEAR/USDT", "ATOM/USDT", "XLM/USDT",
                "OP/USDT", "ARB/USDT", "APE/USDT", "JASMY/USDT", "KUB/USDT"
            ]
            
            valid_pairs = []
            import requests

            print(f"Spy: Scanning {len(candidates)} candidates for Top Volume...")
            
            for symbol in candidates:
                try:
                    # Symbol format for API: BTC/USDT -> BTCUSDT
                    api_symbol = symbol.replace("/", "")
                    url = f"https://api.binance.th/api/v1/ticker/24hr?symbol={api_symbol}"
                    res = requests.get(url, timeout=2).json()
                    
                    if 'quoteVolume' in res:
                        valid_pairs.append({
                            'symbol': symbol,
                            'volume': float(res['quoteVolume'])
                        })
                except: continue
            
            # Sort and Return Top N
            if valid_pairs:
                sorted_pairs = sorted(valid_pairs, key=lambda x: x['volume'], reverse=True)
                top_candidates = sorted_pairs[:limit]
                print(f"Spy: Found Top {len(top_candidates)} Assets: {[p['symbol'] for p in top_candidates]}")
                return top_candidates # Returns List of Dicts [{'symbol': 'BTC/USDT', 'volume': 123}, ...]
            else:
                 # Ultimate Fallback
                 return ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

        except Exception as e:
            print(f"Spy Top Assets Error: {e}")
            return ["BTC/USDT", "ETH/USDT"] # Fallback

    def calculate_indicators(self, df: pd.DataFrame):
        """
        Calculates Technical Indicators (RSI, MACD)
        Note: Since pandas_ta had install issues, we implement basic RSI manually or use fallback.
        """
        if df is None or df.empty:
            return None
        
        # Basic Manual RSI Implementation to avoid dependency hell
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        # MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        
        # Bollinger Bands (20, 2)
        df['sma_20'] = df['close'].rolling(window=20).mean()
        df['std_20'] = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['sma_20'] + (df['std_20'] * 2)
        df['bb_lower'] = df['sma_20'] - (df['std_20'] * 2)
        
        # Fill NaN
        cols = ['rsi', 'ema_20', 'ema_50', 'macd', 'signal', 'bb_upper', 'bb_lower']
        for c in cols:
            df[c] = df[c].bfill().ffill()
        
        return df

if __name__ == "__main__":
    # Test The Spy
    spy = Spy()
    print("Fetching BTC/USDT from Binance TH...")
    data = spy.fetch_ohlcv("BTC/USDT", limit=20)
    if data is not None:
        data = spy.calculate_indicators(data)
        print(data[['timestamp', 'close', 'rsi']].tail())
    else:
        print("Failed to fetch data.")
