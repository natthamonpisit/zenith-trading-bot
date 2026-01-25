import ccxt.pro as ccxt  # Use Pro for potential websocket, but standard ccxt is fine for REST
import ccxt
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()

class Spy:
    """
    The Spy (Data Collector)
    Role: Fetches market data (OHLCV) from the exchange and calculates basic technical indicators.
    """
    def __init__(self, exchange_id='binance'):
        self.api_key = os.environ.get("BINANCE_API_KEY")
        self.secret = os.environ.get("BINANCE_SECRET")
        self.api_url = os.environ.get("BINANCE_API_URL", "https://api.binance.com") # Default to global if not set
        
        # Initialize Exchange
        options = {
            'defaultType': 'spot',
            'fetchCurrencies': False, 
            'fetchMarginPairs': False, # Explicitly disable margin pairs
            'fetchPositions': False,   # Disable positions
        } 
        if "binance.th" in self.api_url or "api.binance.th" in self.api_url:
             # Manual override for Binance TH
             self.exchange = ccxt.binance({
                'apiKey': self.api_key,
                'secret': self.secret,
                'options': options,
             })
             # Aggressive URL override
             # TRICK: Map 'v3' key to 'v1' URL because Binance TH uses v1 for klines
             self.exchange.urls['api'] = {
                'public': 'https://api.binance.th/api/v1',
                'private': 'https://api.binance.th/api/v1',
                'v3': 'https://api.binance.th/api/v1', 
                'v1': 'https://api.binance.th/api/v1',
                'sapi': 'https://api.binance.th/sapi/v1',
                'sapiV1': 'https://api.binance.th/sapi/v1',
             }
             
             # CRITICAL: Manually disable capabilities to prevent auto-fetching missing endpoints
             self.exchange.has['fetchMarginPairs'] = False
             self.exchange.has['fetchPositions'] = False
             self.exchange.has['fetchCurrencies'] = False
             
             # CRITICAL: Manually disable capabilities
             self.exchange.has['fetchMarginPairs'] = False
             self.exchange.has['fetchPositions'] = False
             self.exchange.has['fetchCurrencies'] = False

             
             # CRITICAL: Manually disable capabilities
             self.exchange.has['fetchMarginPairs'] = False
             self.exchange.has['fetchPositions'] = False
             self.exchange.has['fetchCurrencies'] = False

             # DYNAMIC LOAD: Fetch actual exchangeInfo from Binance TH (v1) manually
             # Because CCXT load_markets() fails on sapi/config
             try:
                 import requests
                 print("Spy: Fetching markets from Binance TH (v1/exchangeInfo)...")
                 response = requests.get('https://api.binance.th/api/v1/exchangeInfo')
                 data = response.json()
                 
                 markets_map = {}
                 ids_map = {}
                 currencies_map = {}
                 
                 for s in data['symbols']:
                     if s['status'] != 'TRADING': continue
                     
                     market_id = s['symbol'] # e.g. BTCUSDT
                     base_id = s['baseAsset']
                     quote_id = s['quoteAsset']
                     symbol = f"{base_id}/{quote_id}" # e.g. BTC/USDT
                     
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
                     ids_map[market_id] = symbol
                     
                     # Add currencies
                     if base_id not in currencies_map: currencies_map[base_id] = {'id': base_id}
                     if quote_id not in currencies_map: currencies_map[quote_id] = {'id': quote_id}
                 
                 self.exchange.markets = markets_map
                 self.exchange.ids = ids_map
                 self.exchange.currencies = currencies_map
                 print(f"Spy: Loaded {len(markets_map)} markets from Binance TH.")
                 
             except Exception as e:
                 print(f"Spy: Failed to dynamic load markets: {e}")
                 # Fallback to BTC/USDT if dynamic load fails
                 self.exchange.markets = {
                     'BTC/USDT': {'id': 'BTCUSDT', 'symbol': 'BTC/USDT', 'base': 'BTC', 'quote': 'USDT', 'active': True, 'type': 'spot'}
                 }
                 self.exchange.ids = {'BTCUSDT': 'BTC/USDT'}
        else:
            self.exchange = getattr(ccxt, exchange_id)({
                'apiKey': self.api_key,
                'secret': self.secret,
                'options': options
            })

    def fetch_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 100):
        """
        Fetches OHLCV data.
        :param symbol: e.g. 'BTC/USDT' (Make sure to use TH pairs like BTC/THB if using TH exchange exclusively?) 
                       Wait, Binance TH supports USDT pairs too? Usually yes.
        """
        try:
            # Check market loading
            if not self.exchange.markets:
                self.exchange.load_markets()
            
            # Fetch data
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            # Convert to DataFrame
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            return df
        except Exception as e:
            print(f"Spy (Data Fetch) Error: {e}")
            return None

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
