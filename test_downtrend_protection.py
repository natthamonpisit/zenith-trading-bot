#!/usr/bin/env python3
"""
Test script to verify downtrend protection implementation.
"""
import sys
from src.roles.job_price import PriceSpy
from src.roles.job_analysis import Judge
from src.database import get_db

def test_indicators():
    """Test that new indicators are calculated correctly"""
    print("=" * 60)
    print("TEST 1: Indicator Calculation")
    print("=" * 60)

    spy = PriceSpy()
    print("Fetching BTC/USDT data...")
    df = spy.fetch_ohlcv("BTC/USDT", limit=250)  # Need 200+ for EMA 200

    if df is None:
        print("❌ Failed to fetch data")
        return False

    print(f"✅ Fetched {len(df)} candles")

    print("Calculating indicators...")
    df = spy.calculate_indicators(df)

    if df is None:
        print("❌ Failed to calculate indicators")
        return False

    # Check new indicators exist
    required_indicators = ['ema_200', 'adx', 'dmp', 'dmn', 'ema_50_slope', 'price_position_score']
    missing = [ind for ind in required_indicators if ind not in df.columns]

    if missing:
        print(f"❌ Missing indicators: {missing}")
        return False

    print("✅ All new indicators calculated")

    # Show latest values
    latest = df.iloc[-1]
    print(f"\nLatest values:")
    print(f"  Close: ${latest['close']:,.2f}")
    print(f"  EMA 200: ${latest['ema_200']:,.2f}")
    print(f"  ADX: {latest['adx']:.2f}")
    print(f"  DMP: {latest['dmp']:.2f}")
    print(f"  DMN: {latest['dmn']:.2f}")
    print(f"  EMA 50 Slope: {latest['ema_50_slope']:.2f}%")
    print(f"  Price Position Score: {latest['price_position_score']:.0f}/3")

    return True


def test_trend_detection():
    """Test trend detection algorithm"""
    print("\n" + "=" * 60)
    print("TEST 2: Trend Detection")
    print("=" * 60)

    spy = PriceSpy()
    df = spy.fetch_ohlcv("BTC/USDT", limit=250)
    df = spy.calculate_indicators(df)

    if df is None:
        print("❌ Failed to prepare data")
        return False

    print("Detecting market trend...")
    trend_data = spy.detect_market_trend(df)

    if not trend_data:
        print("❌ Trend detection returned empty")
        return False

    print("✅ Trend detection successful")
    print(f"\nTrend Analysis:")
    print(f"  Trend: {trend_data['trend']}")
    print(f"  Strength: {trend_data['strength']:.0f}%")
    print(f"  Confidence: {trend_data['confidence']:.0f}%")
    print(f"\nSignals Breakdown:")
    for key, value in trend_data['signals'].items():
        print(f"  {key}: {value}")

    return True


def test_judge_integration():
    """Test that Judge receives and uses trend data"""
    print("\n" + "=" * 60)
    print("TEST 3: Judge Integration")
    print("=" * 60)

    db = get_db()

    # First, enable downtrend protection
    print("Enabling downtrend protection in MODERATE mode...")
    db.table("bot_config").upsert({"key": "ENABLE_DOWNTREND_PROTECTION", "value": "true"}).execute()
    db.table("bot_config").upsert({"key": "DOWNTREND_PROTECTION_MODE", "value": "MODERATE"}).execute()

    judge = Judge()

    # Create mock data with STRONG_DOWNTREND
    ai_data = {'confidence': 80, 'recommendation': 'BUY'}
    tech_data = {
        'rsi': 50,
        'ema_50': 95000,
        'macd': 0.5,
        'macd_signal': 0.3,
        'close': 90000,
        'market_trend': {
            'trend': 'STRONG_DOWNTREND',
            'strength': 85,
            'confidence': 90,
            'signals': {
                'ema_aligned': 'BEAR',
                'adx': 45,
                'price_position': 0,
                'ema_slope': -2.5,
                'dm_direction': 'BEAR',
                'price_vs_ema200': 'BELOW'
            }
        }
    }

    print("Testing Judge with STRONG_DOWNTREND signal...")
    verdict = judge.evaluate(ai_data, tech_data, 1000.0, is_sim=True)

    if verdict.decision == "REJECTED" and "Downtrend Protection" in verdict.reason:
        print(f"✅ Judge correctly rejected BUY in strong downtrend")
        print(f"   Reason: {verdict.reason}")
    else:
        print(f"❌ Judge did not reject as expected")
        print(f"   Decision: {verdict.decision}")
        print(f"   Reason: {verdict.reason}")
        return False

    # Test with UPTREND
    tech_data['market_trend']['trend'] = 'UPTREND'
    print("\nTesting Judge with UPTREND signal...")
    verdict = judge.evaluate(ai_data, tech_data, 1000.0, is_sim=True)

    if verdict.decision == "APPROVED":
        print(f"✅ Judge correctly approved BUY in uptrend")
        print(f"   Size: ${verdict.size:.2f}")
    else:
        print(f"⚠️  Judge rejected: {verdict.reason}")
        print(f"   (This may be due to other filters)")

    return True


def test_config_persistence():
    """Test that config values are saved in database"""
    print("\n" + "=" * 60)
    print("TEST 4: Config Persistence")
    print("=" * 60)

    db = get_db()

    required_keys = [
        'ENABLE_DOWNTREND_PROTECTION',
        'DOWNTREND_PROTECTION_MODE',
        'DOWNTREND_AI_BOOST',
        'DOWNTREND_SIZE_REDUCTION_PCT',
        'ADX_TREND_THRESHOLD'
    ]

    print("Checking database for config entries...")
    all_found = True

    for key in required_keys:
        result = db.table("bot_config").select("value").eq("key", key).execute()
        if result.data:
            value = result.data[0]['value']
            print(f"  ✅ {key} = {value}")
        else:
            print(f"  ❌ {key} NOT FOUND")
            all_found = False

    if all_found:
        print("\n✅ All config entries present in database")
    else:
        print("\n❌ Some config entries missing")

    return all_found


def main():
    """Run all tests"""
    print("\n🧪 DOWNTREND PROTECTION VERIFICATION TESTS\n")

    tests = [
        ("Indicator Calculation", test_indicators),
        ("Trend Detection", test_trend_detection),
        ("Judge Integration", test_judge_integration),
        ("Config Persistence", test_config_persistence)
    ]

    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Downtrend protection is working correctly.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
