import importlib
from types import SimpleNamespace

import pandas as pd
import pytest

from src.roles.job_analysis import TradeDecision


class _FakeDBQuery:
    def __init__(self, db, table_name):
        self._db = db
        self._table_name = table_name
        self._filters = {}
        self._action = "select"
        self._payload = None

    def select(self, *_args, **_kwargs):
        self._action = "select"
        return self

    def eq(self, key, value):
        self._filters[key] = value
        return self

    def limit(self, _value):
        return self

    def insert(self, payload):
        self._action = "insert"
        self._payload = payload
        return self

    def upsert(self, payload):
        self._action = "upsert"
        self._payload = payload
        return self

    def execute(self):
        if self._table_name == "assets":
            if self._action == "insert":
                return SimpleNamespace(data=[{"id": "asset-1"}])
            return SimpleNamespace(data=[{"id": "asset-1"}])

        if self._table_name == "bot_config":
            key = self._filters.get("key")
            mapping = {
                "TRADING_MODE": "PAPER",
                "ENABLE_AI_TIERING": "false",
                "AI_MODEL": "GEMINI",
            }
            return SimpleNamespace(data=[{"value": mapping.get(key, "false")}])

        if self._table_name == "simulation_portfolio":
            return SimpleNamespace(data=[{"balance": 1000.0}])

        if self._table_name == "positions":
            return SimpleNamespace(data=[])

        if self._table_name == "trade_signals" and self._action == "insert":
            row = {"id": "signal-1", **(self._payload or {})}
            self._db.inserted_trade_signals.append(row)
            return SimpleNamespace(data=[row])

        return SimpleNamespace(data=[])


class _FakeDB:
    def __init__(self):
        self.inserted_trade_signals = []

    def table(self, table_name):
        return _FakeDBQuery(self, table_name)


class _FakeTelemetry:
    def __init__(self):
        self.feature_calls = 0
        self.score_calls = 0
        self.ai_calls = 0
        self.rule_calls = 0

    def track_ai_decision(self, **_kwargs):
        self.ai_calls += 1
        return {"ok": True}

    def track_feature_snapshot(self, **_kwargs):
        self.feature_calls += 1
        return {"ok": True}

    def track_signal_score(self, **_kwargs):
        self.score_calls += 1
        return {"ok": True}

    def track_rule_evaluation(self, **_kwargs):
        self.rule_calls += 1
        return {"ok": True}


class _FakePriceSpy:
    def fetch_ohlcv(self, _pair, _timeframe, limit=250):
        assert limit >= 250
        return pd.DataFrame(
            [
                {
                    "close": 100.0,
                    "open": 99.0,
                    "high": 101.0,
                    "low": 98.5,
                    "volume": 1200.0,
                    "rsi": 56.0,
                    "macd": 1.1,
                    "signal": 0.9,
                    "ema_20": 99.5,
                    "ema_50": 98.8,
                    "ema_200": 95.0,
                    "atr": 1.6,
                    "adx": 28.0,
                    "dmp": 25.0,
                    "dmn": 18.0,
                    "ema_50_slope": 0.8,
                    "price_position_score": 3.0,
                    "bb_upper": 103.0,
                    "bb_lower": 97.0,
                }
            ]
        )

    def calculate_indicators(self, df):
        return df

    def detect_market_trend(self, _df):
        return {
            "trend": "UPTREND",
            "strength": 65,
            "confidence": 70,
            "signals": {"ema_aligned": "BULL", "price_vs_ema200": "ABOVE", "price_position": 3},
        }


class _FakeStrategist:
    def analyze_market(self, *_args, **_kwargs):
        return {
            "confidence": 82,
            "recommendation": "BUY",
            "sentiment_score": 0.35,
            "reasoning": "test",
        }


class _FakeJudge:
    config = {"AI_CONF_THRESHOLD": "60", "RSI_THRESHOLD": "75"}

    def evaluate(self, *_args, **_kwargs):
        # Reject to avoid execution branch while still testing persistence path.
        return TradeDecision(decision="REJECTED", size=0, reason="unit_test_reject")


@pytest.mark.unit
def test_process_pair_persists_feature_and_signal_score(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_CODING_PLAN_KEY", raising=False)

    main_mod = importlib.import_module("main")
    fake_db = _FakeDB()
    fake_telemetry = _FakeTelemetry()

    monkeypatch.setattr(main_mod, "db", fake_db)
    monkeypatch.setattr(main_mod, "telemetry_tracker", fake_telemetry)
    monkeypatch.setattr(main_mod, "price_spy", _FakePriceSpy())
    monkeypatch.setattr(main_mod, "strategist", _FakeStrategist())
    monkeypatch.setattr(main_mod, "judge", _FakeJudge())
    monkeypatch.setattr(main_mod, "is_ai_tiering_enabled", lambda: False)
    monkeypatch.setattr(main_mod, "get_bot_runtime_status", lambda: "ACTIVE")
    monkeypatch.setattr(main_mod, "get_available_trading_balance", lambda mode, actual_balance: actual_balance)
    monkeypatch.setattr(main_mod, "log_activity", lambda *_args, **_kwargs: None)

    # Should run without raising and persist score-related snapshots.
    main_mod.process_pair("BTC/USDT", "1h", intent="ENTRY")

    assert fake_telemetry.ai_calls == 1
    assert fake_telemetry.feature_calls == 1
    assert fake_telemetry.score_calls == 1
    assert fake_telemetry.rule_calls >= 3
    assert len(fake_db.inserted_trade_signals) == 1
