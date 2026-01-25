import ccxt
import time
import os
from dotenv import load_dotenv

load_dotenv()

def test_connection():
    api_key = os.environ.get("BINANCE_API_KEY")
    secret = os.environ.get("BINANCE_SECRET")
    
    print(f"Testing Binance TH Connection...")
    print(f"KEY: {api_key[:5]}...{api_key[-5:]}")

    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'spot',
            'fetchCurrencies': False, # STOP calling sapi/v1/capital/config/getall
        },
        'urls': {
            'api': {
                'public': 'https://api.binance.th/api/v3',
                'private': 'https://api.binance.th/api/v3',
            },
            'sapi': 'https://api.binance.th/sapi/v1', # Overwrite sapi just in case
        }
    })

    try:
        # 1. Try fetching just the ticker first (Public)
        print("1. Fetching Ticker (BTC/USDT)...")
        ticker = exchange.fetch_ticker('BTC/USDT')
        print(f"   Success! Price: {ticker['last']}")

        # 2. Try fetching OHLCV (Public)
        print("2. Fetching OHLCV (BTC/USDT)...")
        ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1h', limit=3)
        print(f"   Success! Count: {len(ohlcv)}")

        # 3. Try fetching Balance (Private)
        print("3. Fetching Balance...")
        balance = exchange.fetch_balance()
        print("   Success! Balance fetched.")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_connection()
