from src.ai.tiering import TieredAIDecisionEngine


class DummyModel:
    model_name = "dummy-model"


class DummyStrategist:
    def __init__(self):
        self.model = DummyModel()

    def analyze_market(self, snapshot_id, asset_symbol, tech_data, intent="ENTRY"):
        if intent == "EXIT":
            return {
                "recommendation": "SELL",
                "confidence": 72,
                "sentiment_score": -0.2,
                "reasoning": "Exit signal confirmed",
            }
        return {
            "recommendation": "BUY",
            "confidence": 78,
            "sentiment_score": 0.35,
            "reasoning": "Entry signal confirmed",
        }


def _sample_snapshot():
    return {
        "close": {"1": 100.0, "2": 110.0},
        "rsi": {"1": 58.0, "2": 62.0},
        "macd": {"1": 1.2, "2": 1.6},
        "signal": {"1": 1.1, "2": 1.4},
        "ema_20": {"1": 105.0, "2": 108.0},
        "ema_50": {"1": 98.0, "2": 103.0},
        "ema_200": {"1": 90.0, "2": 95.0},
        "atr": {"1": 2.1, "2": 2.2},
        "volume": {"1": 1000.0, "2": 1200.0},
    }


def test_tier_1_summarize_bias():
    engine = TieredAIDecisionEngine(strategist=None)
    summary = engine.tier_1_summarize(symbol="BTC/USDT", tech_snapshot=_sample_snapshot(), intent="ENTRY")
    assert summary["trend_bias"] == "BULLISH"
    assert summary["momentum_bias"] == "BULLISH"
    assert summary["token_estimate"] > 0


def test_tier_3_govern_blocks_low_confidence():
    engine = TieredAIDecisionEngine(strategist=None)
    governed = engine.tier_3_govern(
        tier_2={
            "recommendation": "BUY",
            "confidence": 40,
            "sentiment_score": 0.1,
            "reasoning": "weak",
        },
        intent="ENTRY",
        config={"AI_CONF_THRESHOLD": "60"},
    )
    assert governed["recommendation"] == "WAIT"
    assert "LOW_CONFIDENCE" in governed["veto_reasons"]


def test_evaluate_and_telemetry_rows():
    engine = TieredAIDecisionEngine(strategist=DummyStrategist())
    result = engine.evaluate(
        symbol="BTC/USDT",
        tech_snapshot=_sample_snapshot(),
        intent="ENTRY",
        config={"AI_CONF_THRESHOLD": "60"},
    )
    assert result["final"]["recommendation"] == "BUY"
    assert result["run_id"]
    t1, t2, t3 = engine.to_telemetry_records(result=result, symbol="BTC/USDT", timeframe="1h")
    assert t1["tier"] == "TIER_1_SUMMARIZER"
    assert t2["tier"] == "TIER_2_DECISION"
    assert t3["tier"] == "TIER_3_GOVERNOR"
