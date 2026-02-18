from unittest.mock import Mock

from src.telemetry.tracker import TelemetryTracker


def _build_table_mock(execute_data=None):
    table = Mock()
    table.select.return_value = table
    table.order.return_value = table
    table.limit.return_value = table
    table.eq.return_value = table
    table.insert.return_value = table
    table.execute.return_value = Mock(data=execute_data or [])
    return table


def test_track_ai_decision_insert():
    db = Mock()
    ai_table = _build_table_mock(execute_data=[{"id": "1"}])
    db.table.return_value = ai_table

    tracker = TelemetryTracker(db=db)
    result = tracker.track_ai_decision(
        run_id="11111111-1111-1111-1111-111111111111",
        symbol="BTC/USDT",
        timeframe="1h",
        tier="TIER_2_DECISION",
        model="gemini",
        prompt={"p": 1},
        input_payload={"x": 1},
        output_json={"recommendation": "BUY"},
        confidence=80.0,
        latency_ms=120,
    )

    assert result["ok"] is True
    db.table.assert_called_with("ai_decisions")
    assert ai_table.insert.called


def test_get_rule_evaluations_with_filters():
    db = Mock()
    table = _build_table_mock(execute_data=[{"id": "r1", "rule_name": "AI_CONF_THRESHOLD"}])
    db.table.return_value = table

    tracker = TelemetryTracker(db=db)
    rows = tracker.get_rule_evaluations(
        symbol="BTC/USDT",
        run_id="11111111-1111-1111-1111-111111111111",
        rule_name="AI_CONF_THRESHOLD",
        limit=10,
    )

    assert len(rows) == 1
    assert rows[0]["rule_name"] == "AI_CONF_THRESHOLD"
    assert table.eq.call_count == 3


def test_replay_bundle_shape():
    db = Mock()
    table = _build_table_mock(execute_data=[])
    db.table.return_value = table
    tracker = TelemetryTracker(db=db)

    bundle = tracker.get_replay_bundle("11111111-1111-1111-1111-111111111111", limit=5)
    assert bundle["run_id"] == "11111111-1111-1111-1111-111111111111"
    assert "ai_decisions" in bundle
    assert "rule_evaluations" in bundle
    assert "post_trade_attribution" in bundle
