from types import SimpleNamespace

import pytest

from src.roles.order_planner import OrderPlanner


class _CfgQuery:
    def __init__(self, rows):
        self._rows = rows
        self._payload = None

    def select(self, *_args):
        return self

    def insert(self, payload):
        self._payload = payload
        return self

    def execute(self):
        if self._payload is not None:
            return SimpleNamespace(data=[{"id": "plan-1"}])
        return SimpleNamespace(data=self._rows)


class _FakeDB:
    def __init__(self, cfg_rows):
        self.cfg_rows = cfg_rows
        self.last_insert_payload = None

    def table(self, table_name):
        if table_name == "bot_config":
            return _CfgQuery(self.cfg_rows)
        if table_name == "order_plans":
            query = _CfgQuery([])
            original_insert = query.insert

            def _insert(payload):
                self.last_insert_payload = payload
                return original_insert(payload)

            query.insert = _insert
            return query
        raise AssertionError(f"unexpected table: {table_name}")


@pytest.mark.unit
def test_build_plan_buy_contains_sl_tp_and_breakeven():
    db = _FakeDB(
        cfg_rows=[
            {"key": "STOP_LOSS_ATR_MULTIPLIER", "value": "2.0"},
            {"key": "MIN_STOP_LOSS_PCT", "value": "1.0"},
            {"key": "TP1_R_MULTIPLE", "value": "1.0"},
            {"key": "TP2_R_MULTIPLE", "value": "2.0"},
            {"key": "TP1_PARTIAL_PCT", "value": "40"},
            {"key": "BREAKEVEN_BUFFER_PCT", "value": "0.2"},
        ]
    )
    planner = OrderPlanner(db=db)

    plan = planner.build_plan(
        symbol="BTC/USDT",
        side="BUY",
        timeframe="1h",
        entry_price=100.0,
        tech_data={"atr": 2.5, "rsi": 55, "adx": 30},
        run_id="run-1",
        asset_id="asset-1",
    )

    assert plan["symbol"] == "BTC/USDT"
    assert plan["stop_loss"] < plan["entry_price"]
    assert plan["take_profit_1"] > plan["entry_price"]
    assert plan["take_profit_2"] > plan["take_profit_1"]
    assert plan["tp1_partial_pct"] == 40.0
    assert plan["breakeven_price"] > plan["entry_price"]


@pytest.mark.unit
def test_persist_plan_returns_id():
    db = _FakeDB(cfg_rows=[])
    planner = OrderPlanner(db=db)
    plan_id = planner.persist_plan(
        {
            "run_id": "run-1",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "entry_price": 100.0,
        }
    )
    assert plan_id == "plan-1"
    assert db.last_insert_payload["symbol"] == "BTC/USDT"
