import ccxt # Standard CCXT (Free Version)
import time
import pandas as pd
try:
    import pandas_ta as ta # Financial Technical Analysis Library
except ImportError:
    import pandas_ta_classic as ta # Fallback to community fork
import os
from dotenv import load_dotenv

# Error handling utilities
from src.utils import CircuitBreaker, SimpleCache, ExternalAPIError, retry_with_backoff, RateLimiter
from src.utils.logger import get_logger, log_execution_time

load_dotenv()

class PriceSpy:
    """
    THE SPY A (Price Collector)
    Role: Fetches market data (OHLCV) from the exchange and calculates basic technical indicators.
    """
    def __init__(self, exchange_id='binance'):
        # Initialize logger
        self.logger = get_logger(__name__, role="Spy")
        
        self.api_key = os.environ.get("BINANCE_API_KEY")
        self.secret = os.environ.get("BINANCE_SECRET")
        self.api_url = os.environ.get("BINANCE_API_URL", "https://api.binance.com")
        
        # Circuit breaker for CCXT API protection
        self.ccxt_breaker = CircuitBreaker(
            name="CCXT_API",
            failure_threshold=5,
            timeout=60.0
        )
        
        
        # Cache for ticker data (short TTL to reduce API calls)
        self.ticker_cache = SimpleCache(default_ttl=5.0, max_size=500)
        
        # Rate limiter: Binance allows 1200 requests/minute
        # Set to 1000 to be safe with buffer
        self.rate_limiter = RateLimiter(max_calls=1000, period=60.0)
        
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
                'timeout': 10000, 
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot',
                    'fetchCurrencies': False,
                    'fetchMarginPairs': False,
                    'fetchPositions': False,
                    'warnOnFetchMarginPairs': False,
                    'adjustForTimeDifference': True,
                    'recvWindow': 10000,
                    'createMarketBuyOrderRequiresPrice': False, # Binance spot market buy doesn't need price
                }
             })
             # Override URLs map manually to point to TH
             # TEST RESULT: api/v3 is 404. api/v1 is 200. We MUST alias v3 -> v1.
             self.exchange.urls['api'] = {
                'public': 'https://api.binance.th/api/v1', 
                'private': 'https://api.binance.th/api/v1',
                'v3': 'https://api.binance.th/api/v1', # Alias v3 to v1
                'v1': 'https://api.binance.th/api/v1',
                'sapi': 'https://api.binance.th/api/v1', # Alias SAPI to API v1 to prevent "missing URL" error
                'fapiPublic': 'https://api.binance.th/api/v1', 
                'fapiPrivate': 'https://api.binance.th/api/v1',
                'dapiPublic': 'https://api.binance.th/api/v1',
                'dapiPrivate': 'https://api.binance.th/api/v1',
             }
             # Strictly disable all non-spot features
             self.exchange.has['fetchMarginPairs'] = False
             self.exchange.has['fetchPositions'] = False
             self.exchange.has['fetchCurrencies'] = False
             self.exchange.has['fetchIsolatedMarginPairs'] = False
             self.exchange.has['fetchCrossMarginPairs'] = False
             self.exchange.has['margin'] = False # Explicitly disable margin capability
             self.exchange.has['swap'] = False
             self.exchange.has['future'] = False
        else:
             self.exchange = getattr(ccxt, exchange_id)({
                'apiKey': self.api_key,
                'secret': self.secret,
                'options': options
            })

    def _fetch_ticker_protected(self, symbol: str):
        """
        Fetch single ticker with circuit breaker and cache protection.
        
        Args:
            symbol: Trading pair symbol (e.g. 'BTC/USDT')
            
        Returns:
            Ticker dict or None if failed
        """
        # Try cache first
        cache_key = f"ticker:{symbol}"
        cached = self.ticker_cache.get(cache_key)
        if cached is not None:
            return cached
        
        # Fetch with circuit breaker
        try:
            ticker = self.ccxt_breaker.call_function(
                lambda: self.exchange.fetch_ticker(symbol)
            )
            # Cache for 5 seconds
            self.ticker_cache.set(cache_key, ticker, ttl=5)
            return ticker
        except Exception as e:
            # Log error with context
            print(f"⚠️ [CCXT Error] fetch_ticker({symbol}) failed: {e}")
            # Return cached value if available (stale better than nothing)
            return cached

    def _fetch_tickers_protected(self):
        """
        Fetch all tickers with circuit breaker protection.
        
        Returns:
            Dict of tickers or empty dict if failed
        """
        cache_key = "tickers:all"
        cached = self.ticker_cache.get(cache_key)
        if cached is not None:
            return cached
        
        try:
            tickers = self.ccxt_breaker.call_function(
                lambda: self.exchange.fetch_tickers()
            )
            # Cache for 5 seconds
            self.ticker_cache.set(cache_key, tickers, ttl=5)
            return tickers
        except Exception as e:
            print(f"⚠️ [CCXT Error] fetch_tickers() failed: {e}")
            # Return cached or empty dict
            return cached or {}


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
            ticker = self._fetch_ticker_protected('USDT/THB')
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
                    all_tickers = self._fetch_tickers_protected()
                    
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
                            ticker = self._fetch_ticker_protected(symbol)
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
            df['ema_200'] = df.ta.ema(length=200)  # Long-term trend baseline

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

            # 6. ADX (Average Directional Index) - Trend strength
            adx_data = df.ta.adx(length=14)
            if adx_data is not None:
                df['adx'] = adx_data['ADX_14']
                df['dmp'] = adx_data['DMP_14']  # Directional Movement Positive
                df['dmn'] = adx_data['DMN_14']  # Directional Movement Negative

            # 7. EMA 50 Slope (momentum of trend) - 5-period rate of change
            df['ema_50_slope'] = df['ema_50'].pct_change(periods=5) * 100

            # 8. Price Position Score (0-3: how many EMAs price is above)
            def calc_price_position(close, ema_20, ema_50, ema_200):
                score = 0
                if close > ema_20: score += 1
                if close > ema_50: score += 1
                if close > ema_200: score += 1
                return score

            df['price_position_score'] = df.apply(
                lambda row: calc_price_position(
                    row['close'], row['ema_20'], row['ema_50'], row['ema_200']
                ), axis=1
            )

            # 9. Fill NaN (backfill first to avoid dropping initial rows)
            df = df.bfill().ffill()
            
            return df
            
        except Exception as e:
            print(f"Indicator Calc Error (Pandas-TA): {e}")
            # Fallback not needed if library is installed, but return original df to prevent crash
            return df

    def detect_market_trend(self, df: pd.DataFrame) -> dict:
        """
        Hybrid Trend Detection using EMA alignment, ADX, price position, and momentum.

        Combines multiple indicators to classify market trend:
        - EMA Alignment (structural trend)
        - ADX (trend strength)
        - Price Position (bullish/bearish structure)
        - EMA Slope (momentum direction)
        - Directional Movement (positive vs negative pressure)

        Returns:
            {
                'trend': 'STRONG_UPTREND' | 'UPTREND' | 'NEUTRAL' | 'DOWNTREND' | 'STRONG_DOWNTREND',
                'strength': float (0-100),
                'confidence': float (0-100),
                'signals': dict (breakdown of detection components)
            }
        """
        if df is None or df.empty or len(df) < 200:
            return {'trend': 'NEUTRAL', 'strength': 0, 'confidence': 0, 'signals': {}}

        latest = df.iloc[-1]

        # Extract indicators
        ema_20 = latest.get('ema_20', 0)
        ema_50 = latest.get('ema_50', 0)
        ema_200 = latest.get('ema_200', 0)
        close = latest.get('close', 0)
        adx = latest.get('adx', 0)
        dmp = latest.get('dmp', 0)
        dmn = latest.get('dmn', 0)
        ema_slope = latest.get('ema_50_slope', 0)
        price_pos = latest.get('price_position_score', 0)

        # Component checks
        ema_aligned_bull = (ema_20 > ema_50 > ema_200)
        ema_aligned_bear = (ema_20 < ema_50 < ema_200)
        is_trending = adx > 25
        is_strong_trend = adx > 40
        dm_bullish = dmp > dmn

        # Scoring system (-100 to +100)
        trend_score = 0

        # Price vs EMA200 (±30 points)
        if close > ema_200:
            trend_score += 30
        elif close < ema_200:
            trend_score -= 30

        # EMA Alignment (±25 points)
        if ema_aligned_bull:
            trend_score += 25
        elif ema_aligned_bear:
            trend_score -= 25

        # ADX Strength (±20 points)
        if is_trending:
            direction = 1 if dm_bullish else -1
            strength_mult = min(adx / 50, 1.0)
            trend_score += direction * 20 * strength_mult

        # EMA Slope (±15 points)
        if ema_slope > 0.5:
            trend_score += 15
        elif ema_slope < -0.5:
            trend_score -= 15

        # Price Position (±10 points)
        trend_score += (price_pos - 1.5) * 6.67

        # Normalize and classify
        trend_score = max(-100, min(100, trend_score))

        if trend_score >= 60:
            trend = 'STRONG_UPTREND'
        elif trend_score >= 20:
            trend = 'UPTREND'
        elif trend_score >= -20:
            trend = 'NEUTRAL'
        elif trend_score >= -60:
            trend = 'DOWNTREND'
        else:
            trend = 'STRONG_DOWNTREND'

        # Calculate confidence
        confidence = 0
        if ema_aligned_bull or ema_aligned_bear:
            confidence += 40
        if is_trending:
            confidence += 30
        if is_strong_trend:
            confidence += 30
        confidence = min(100, confidence)

        return {
            'trend': trend,
            'strength': abs(trend_score),
            'confidence': confidence,
            'signals': {
                'ema_aligned': 'BULL' if ema_aligned_bull else ('BEAR' if ema_aligned_bear else 'NONE'),
                'adx': adx,
                'price_position': price_pos,
                'ema_slope': ema_slope,
                'dm_direction': 'BULL' if dm_bullish else 'BEAR',
                'price_vs_ema200': 'ABOVE' if close > ema_200 else 'BELOW'
            }
        }

if __name__ == "__main__":
    # Test The Spy
    spy = PriceSpy()
    print("Fetching BTC/USDT from Binance TH...")
    data = spy.fetch_ohlcv("BTC/USDT", limit=20)
    if data is not None:
        data = spy.calculate_indicators(data)
        print(data[['timestamp', 'close', 'rsi']].tail())
    else:
        print("Failed to fetch data.")
