"""
Script to test Binance TH Ticker API directly
"""
import requests
import json

def test_ticker():
    symbol = "BTCUSDT"
    print(f"Testing Ticker for {symbol} on Binance TH...")
    
    # URL 1: Ticker 24hr
    url1 = f"https://api.binance.th/api/v1/ticker/24hr?symbol={symbol}"
    print(f"\n1. Requesting: {url1}")
    try:
        res = requests.get(url1, timeout=5)
        print(f"Status: {res.status_code}")
        if res.status_code == 200:
            print(json.dumps(res.json(), indent=2))
        else:
            print(res.text)
    except Exception as e:
        print(f"Error: {e}")
        
    # URL 2: Ticker Price
    url2 = f"https://api.binance.th/api/v1/ticker/price?symbol={symbol}"
    print(f"\n2. Requesting: {url2}")
    try:
        res = requests.get(url2, timeout=5)
        print(f"Status: {res.status_code}")
        if res.status_code == 200:
            print(json.dumps(res.json(), indent=2))
        else:
            print(res.text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_ticker()
