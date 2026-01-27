import ccxt # Standard CCXT (Free Version)
import time
import pandas as pd
try:
    import pandas_ta as ta # Financial Technical Analysis Library
except ImportError:
    import pandas_ta_classic as ta # Fallback to community fork
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
             # TEST RESULT: api/v3 is 404. api/v1 is 200. We MUST alias v3 -> v1.
             self.exchange.urls['api'] = {
                'public': 'https://api.binance.th/api/v1', 
                'private': 'https://api.binance.th/api/v1',
                'v3': 'https://api.binance.th/api/v1', # Alias v3 to v1
                'v1': 'https://api.binance.th/api/v1',
                'sapi': 'https://api.binance.th/sapi/v1',
                'fapiPublic': 'https://api.binance.th/api/v1', # Polyfill to satisfy CCXT validation
                'fapiPrivate': 'https://api.binance.th/api/v1',
                'dapiPublic': 'https://api.binance.th/api/v1',
                'dapiPrivate': 'https://api.binance.th/api/v1',
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
        except Exception as e:
            print(f"Spy: USDT/THB rate fetch error: {e}")
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

    def get_top_symbols(self, limit=30, callback=None, logger=None):
        """Fetches top USDT pairs by 24h Volume"""
        try:
            if not self.exchange.markets:
                self.load_markets_custom()

            # DYNAMIC MARKET SCANNING (User Request)
            # Fetch all available symbols from exchange directly
            if not self.exchange.markets:
                self.exchange.load_markets()
            
            all_symbols = [s for s in self.exchange.symbols if '/USDT' in s]
            
            # Logic: If limit is small (Scanner Mode), use hardcoded 'Safe List' for speed
            # If limit is large (Farming Mode), scan EVERYTHING.
            if limit < 20: 
                 # Fallback/Speed list
                 target_list = [
                    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", 
                    "DOGE/USDT", "ADA/USDT", "LINK/USDT", "DOT/USDT", "POL/USDT"
                 ]
            else:
                 # FULL SCAN
                 target_list = all_symbols
                 if callback: callback(f"Radar: Reading entire market ({len(target_list)} pairs)...")
            
            valid_pairs = []

            # Batch Fetch for Speed & Reliability
            print(f"Spy: Scanning {len(target_list)} candidates...")
            if callback: callback(f"Radar: Bulk scanning {len(target_list)} pairs...")

            # Binance TH doesn't support batch ticker fetch (requires symbol parameter)
            # Skip batch fetch and go straight to individual requests
            if "binance.th" in self.api_url or "api.binance.th" in self.api_url:
                print(f"Spy: Binance TH detected - using individual ticker requests...")
                if logger: logger("Spy", f"Binance TH: Fetching {len(target_list)} tickers individually (no batch endpoint).", "INFO")
                
                total = len(target_list)
                for idx, symbol in enumerate(target_list, 1):
                    try:
                        ticker = self.exchange.fetch_ticker(symbol)
                        vol = 0
                        if 'quoteVolume' in ticker and ticker['quoteVolume']:
                            vol = float(ticker['quoteVolume'])
                        elif 'baseVolume' in ticker and 'last' in ticker:
                            vol = float(ticker['baseVolume']) * float(ticker['last'])
                        
                        if vol > 0: 
                            valid_pairs.append({'symbol': symbol, 'volume': vol})
                        
                        # Show progress every 20 symbols or at completion
                        if idx % 20 == 0 or idx == total:
                            progress_pct = (idx * 100) // total
                            progress_msg = f"Radar: Fetching tickers {idx}/{total} ({progress_pct}%)..."
                            print(f"Spy: Progress: {idx}/{total} ({progress_pct}%)")
                            if callback: callback(progress_msg)
                            
                    except Exception as loop_e:
                        pass # Silent skip to avoid log spam
                    time.sleep(0.15)  # Rate limit: ~6 requests/sec to avoid Binance TH throttle

                print(f"Spy: Successfully fetched {len(valid_pairs)} valid pairs individually.")
            else:
                # Binance Global or other exchanges: Try batch fetch via CCXT
                try:
                    print(f"Spy: Fetching all market tickers via CCXT...")
                    all_tickers = self.exchange.fetch_tickers()
                    
                    # Filter only symbols in our target_list
                    for symbol in target_list:
                        if symbol in all_tickers:
                            ticker = all_tickers[symbol]
                            try:
                                vol = 0
                                if 'quoteVolume' in ticker and ticker['quoteVolume']:
                                    vol = float(ticker['quoteVolume'])
                                elif 'baseVolume' in ticker and 'last' in ticker:
                                    vol = float(ticker['baseVolume']) * float(ticker['last'])
                                
                                if vol > 0:
                                    valid_pairs.append({'symbol': symbol, 'volume': vol})
                            except Exception as e:
                                print(f"Spy: Ticker parse error for {symbol}: {e}")
                    
                    print(f"Spy: Successfully processed {len(valid_pairs)} valid pairs from batch fetch.")
                            
                except Exception as e:
                    # Fallback to loop if batch fetch completely fails
                    if logger: logger("Spy", f"Batch Fetch Failed: {e}. Switching to Loop for {len(target_list)} items.", "WARNING")
                    print(f"Spy: Batch fetch failed, falling back to individual requests...")
                    
                    for symbol in target_list:
                        try:
                            ticker = self.exchange.fetch_ticker(symbol)
                            vol = 0
                            if 'quoteVolume' in ticker and ticker['quoteVolume']:
                                vol = float(ticker['quoteVolume'])
                            elif 'baseVolume' in ticker and 'last' in ticker:
                                vol = float(ticker['baseVolume']) * float(ticker['last'])
                            
                            if vol > 0: 
                                valid_pairs.append({'symbol': symbol, 'volume': vol})
                        except Exception as loop_e:
                            pass # Silent skip in fallback loop to avoid log spam
                        time.sleep(0.15)  # Rate limit for fallback loop

            # Sort by Volume Descending
            valid_pairs.sort(key=lambda x: x['volume'], reverse=True)
            
            if valid_pairs:
                if callback: callback(f"Radar: Found {len(valid_pairs)} valid candidates.")
                print(f"Spy: Found {len(valid_pairs)} valid candidates.")
                return valid_pairs
            
            # Ultimate Fallback
            return [{'symbol': "BTC/USDT", 'volume': 0}, {'symbol': "ETH/USDT", 'volume': 0}]

        except Exception as e:
            print(f"Spy Top Assets Error: {e}")
            return [{'symbol': "BTC/USDT", 'volume': 0}, {'symbol': "ETH/USDT", 'volume': 0}] # Fallback

    def calculate_indicators(self, df: pd.DataFrame):
        """
        Calculates Technical Indicators using PANDAS-TA (Industry Standard Library).
        Features: RSI, MACD, Bollinger Bands, EMA, ATR.
        """
        if df is None or df.empty:
            return None
        
        try:
            # 1. RSI (Relative Strength Index) - Standard length 14
            df['rsi'] = df.ta.rsi(length=14)
            
            # 2. EMA (Exponential Moving Average)
            df['ema_20'] = df.ta.ema(length=20)
            df['ema_50'] = df.ta.ema(length=50)
            
            # 3. MACD (Moving Average Convergence Divergence)
            # Returns a DataFrame with columns: MACD_12_26_9, MACDh_12_26_9 (hist), MACDs_12_26_9 (signal)
            macd = df.ta.macd(fast=12, slow=26, signal=9)
            if macd is not None:
                df['macd'] = macd['MACD_12_26_9']
                df['signal'] = macd['MACDs_12_26_9']
                # macd['MACDh_12_26_9'] is the histogram
                
            # 4. ATR (Average True Range) - Volatility measure, length 14
            df['atr'] = df.ta.atr(length=14)

            # 5. Bollinger Bands (20, 2)
            # Returns BBL (Lower), BBM (Mid), BBU (Upper)
            bb = df.ta.bbands(length=20, std=2)
            if bb is not None:
                df['bb_upper'] = bb['BBU_20_2.0']
                df['bb_lower'] = bb['BBL_20_2.0']
                df['sma_20'] = bb['BBM_20_2.0'] # Middleware is Simple Moving Average
            
            # 5. Fill NaN (backfill first to avoid dropping initial rows)
            df = df.bfill().ffill()
            
            return df
            
        except Exception as e:
            print(f"Indicator Calc Error (Pandas-TA): {e}")
            # Fallback not needed if library is installed, but return original df to prevent crash
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
