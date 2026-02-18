from src.roles.job_analysis import Strategist


class _DummyGeminiModel:
    model_name = "gemini-2.0-flash"


def _build_strategist(minimax_key="sk-cp-test"):
    strategist = Strategist.__new__(Strategist)
    strategist.minimax_coding_key = minimax_key
    strategist.minimax_model = "MiniMax-M2.5"
    strategist.minimax_base_url = "https://api.minimax.io/v1"
    strategist.minimax_timeout_sec = 10
    strategist.minimax_complexity_threshold = 10
    strategist.prefer_minimax_for_decision = True
    strategist.model = _DummyGeminiModel()
    strategist.db = None
    strategist.last_model_used = "UNSET"
    strategist._mark_active_model = lambda model_name: setattr(strategist, "last_model_used", model_name)
    return strategist


def _sample_tech_data():
    return {
        "price": 100.0,
        "rsi": 54.2,
        "macd": 0.14,
        "signal": 0.11,
        "ema_20": 98.0,
        "ema_50": 96.0,
        "ema_200": 90.0,
        "atr": 2.1,
        "volume": 120000.0,
        "trend_bias": "BULLISH",
        "momentum_bias": "BULLISH",
    }


def test_analyze_market_prefers_minimax_for_complex_payload():
    strategist = _build_strategist(minimax_key="sk-cp-test")
    strategist._analyze_with_minimax_coding = lambda prompt: {
        "sentiment_score": 0.35,
        "confidence": 82,
        "reasoning": "Multi-factor signal aligned",
        "recommendation": "BUY",
    }
    strategist._analyze_market_gemini = lambda prompt: {
        "sentiment_score": 0.1,
        "confidence": 65,
        "reasoning": "Gemini fallback",
        "recommendation": "WAIT",
    }

    result = strategist.analyze_market(
        snapshot_id=None,
        asset_symbol="BTC/USDT",
        tech_data=_sample_tech_data(),
        intent="ENTRY",
    )

    assert result["recommendation"] == "BUY"
    assert result["model"] == "MINIMAX_CODING:MiniMax-M2.5"
    assert strategist.last_model_used == "MINIMAX_CODING:MiniMax-M2.5"


def test_analyze_market_falls_back_to_gemini_when_minimax_fails():
    strategist = _build_strategist(minimax_key="sk-cp-test")

    def _raise(_prompt):
        raise RuntimeError("minimax unavailable")

    strategist._analyze_with_minimax_coding = _raise
    strategist._analyze_market_gemini = lambda prompt: {
        "sentiment_score": -0.05,
        "confidence": 71,
        "reasoning": "Gemini rescue path",
        "recommendation": "SELL",
    }

    result = strategist.analyze_market(
        snapshot_id=None,
        asset_symbol="ETH/USDT",
        tech_data=_sample_tech_data(),
        intent="EXIT",
    )

    assert result["recommendation"] == "SELL"
    assert result["model"] == "gemini-2.0-flash"
    assert strategist.last_model_used == "gemini-2.0-flash"


def test_extract_json_object_handles_wrapped_response():
    wrapped = "<think>analysis</think>\n```json\n{\"confidence\": 77, \"recommendation\": \"BUY\"}\n```"
    parsed = Strategist._extract_json_object(wrapped)
    assert parsed["confidence"] == 77
    assert parsed["recommendation"] == "BUY"
