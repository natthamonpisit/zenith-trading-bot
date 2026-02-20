from types import SimpleNamespace

import pytest

from src.roles.signal_scoring import ScoreConfig, SignalScorer, calculate_signal_score


def _bullish_tech_data():
    return {
        "close": 102.0,
        "ema_20": 100.0,
        "ema_50": 98.0,
        "ema_200": 92.0,
        "rsi": 56.0,
        "macd": 1.25,
        "macd_signal": 0.95,
        "atr": 1.65,
        "adx": 31.0,
        "volume": 2500.0,
        "price_position_score": 3.0,
        "bb_upper": 106.0,
        "bb_lower": 98.0,
        "market_trend": {"trend": "UPTREND"},
    }


@pytest.mark.unit
def test_calculate_signal_score_bullish_setup_passes_threshold():
    config = ScoreConfig(min_total_score=60.0, liquidity_min_volume=10000.0)
    result = calculate_signal_score(
        tech_data=_bullish_tech_data(),
        ai_data={"confidence": 78, "sentiment_score": 0.4},
        candidate_meta={"quote_volume": 320000.0},
        config=config,
    )

    assert result.passed_threshold is True
    assert result.total_score >= 60.0
    assert result.component_scores["trend"] > 70.0
    assert result.component_scores["liquidity"] > 70.0


@pytest.mark.unit
def test_calculate_signal_score_penalizes_low_liquidity():
    config = ScoreConfig(min_total_score=60.0, liquidity_min_volume=10000.0)
    base_ai = {"confidence": 78, "sentiment_score": 0.4}

    rich_liquidity = calculate_signal_score(
        tech_data=_bullish_tech_data(),
        ai_data=base_ai,
        candidate_meta={"quote_volume": 320000.0},
        config=config,
    )
    poor_liquidity = calculate_signal_score(
        tech_data=_bullish_tech_data(),
        ai_data=base_ai,
        candidate_meta={"quote_volume": 1200.0},
        config=config,
    )

    assert poor_liquidity.component_scores["liquidity"] < rich_liquidity.component_scores["liquidity"]
    assert poor_liquidity.total_score < rich_liquidity.total_score


@pytest.mark.unit
def test_score_config_from_map_reads_weights_threshold_and_gate():
    config = ScoreConfig.from_map(
        {
            "MIN_TOTAL_SCORE_TO_CANDIDATE": "72",
            "ENABLE_SIGNAL_SCORE_GATE": "true",
            "MIN_VOLUME": "15000",
            "SCORE_WEIGHT_TREND": "30",
            "SCORE_WEIGHT_MOMENTUM": "22",
            "SCORE_WEIGHT_VOLATILITY": "14",
            "SCORE_WEIGHT_LIQUIDITY": "18",
            "SCORE_WEIGHT_STRUCTURE": "8",
            "SCORE_WEIGHT_PORTFOLIO": "8",
        }
    )

    assert config.min_total_score == 72.0
    assert config.enable_score_gate is True
    assert config.liquidity_min_volume == 15000.0
    assert config.weight_trend == 30.0
    assert config.weight_portfolio == 8.0


@pytest.mark.unit
def test_score_config_clamps_out_of_range_values():
    config = ScoreConfig.from_map(
        {
            "MIN_TOTAL_SCORE_TO_CANDIDATE": "170",
            "SCORE_WEIGHT_TREND": "-20",
            "SCORE_WEIGHT_MOMENTUM": "250",
        }
    )

    assert config.min_total_score == 100.0
    assert config.weight_trend == 0.0
    assert config.weight_momentum == 100.0


class _ConfigQuery:
    def __init__(self, rows):
        self._rows = rows

    def select(self, _fields):
        return self

    def execute(self):
        return SimpleNamespace(data=self._rows)


class _ConfigDB:
    def __init__(self, rows):
        self._rows = rows

    def table(self, table_name):
        assert table_name == "bot_config"
        return _ConfigQuery(self._rows)


@pytest.mark.unit
def test_signal_scorer_loads_config_from_db():
    db = _ConfigDB(
        rows=[
            {"key": "MIN_TOTAL_SCORE_TO_CANDIDATE", "value": "65"},
            {"key": "ENABLE_SIGNAL_SCORE_GATE", "value": "true"},
            {"key": "SCORE_WEIGHT_TREND", "value": "28"},
        ]
    )
    scorer = SignalScorer(db=db, cache_ttl_sec=300)

    config = scorer.load_config(force=True)
    assert config.min_total_score == 65.0
    assert config.enable_score_gate is True
    assert config.weight_trend == 28.0
