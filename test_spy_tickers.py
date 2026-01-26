from src.roles.job_price import PriceSpy
import json

spy = PriceSpy()
print("Spy Initialized. Fetching Top Symbols...")
try:
    symbols = spy.get_top_symbols(limit=5)
    print(f"Result: {symbols}")

    print("\n--- Diagnostic: Raw Ticker Data (First 3) ---")
    tickers = spy.exchange.fetch_tickers()
    count = 0
    for s, t in tickers.items():
        if "/USDT" in s:
            print(f"Symbol: {s} | Vol: {t.get('quoteVolume')} | Keys: {list(t.keys())}")
            count += 1
            if count >= 3: break
    
    if count == 0:
        print("WARNING: No symbols found with '/USDT'. Printing first 3 raw symbols:")
        count = 0
        for s, t in tickers.items():
            print(f"Raw Symbol: {s}")
            count += 1
            if count >= 3: break

except Exception as e:
    print(f"Error: {e}")
