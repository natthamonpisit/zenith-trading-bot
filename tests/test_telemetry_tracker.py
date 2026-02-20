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
    assert "feature_snapshots" in bundle
    assert "signal_scores" in bundle
    assert "order_plans" in bundle


def test_track_feature_snapshot_insert():
    db = Mock()
    feature_table = _build_table_mock(execute_data=[{"id": "f1"}])
    db.table.return_value = feature_table

    tracker = TelemetryTracker(db=db)
    result = tracker.track_feature_snapshot(
        run_id="run-1",
        symbol="BTC/USDT",
        timeframe="1h",
        features={
            "close": 60000,
            "volume": 1000,
            "quote_volume": 60000000,
            "rsi": 55,
            "macd": 1.1,
            "macd_signal": 0.9,
        },
        ai_confidence=72,
        sentiment_score=0.2,
    )

    assert result["ok"] is True
    db.table.assert_called_with("feature_snapshot")
    assert feature_table.insert.called


def test_track_signal_score_insert():
    db = Mock()
    score_table = _build_table_mock(execute_data=[{"id": "s1"}])
    db.table.return_value = score_table

    tracker = TelemetryTracker(db=db)
    result = tracker.track_signal_score(
        run_id="run-1",
        symbol="BTC/USDT",
        timeframe="1h",
        total_score=71.5,
        threshold=60,
        passed_threshold=True,
        component_scores={"trend": 80},
        weighted_scores={"trend": 20},
        weights={"trend": 25},
        notes=["ok"],
    )

    assert result["ok"] is True
    db.table.assert_called_with("signal_score")
    assert score_table.insert.called


def test_track_universe_snapshot_rows_uses_bulk_insert():
    db = Mock()
    table = _build_table_mock(execute_data=[{"id": "u1"}])
    db.table.return_value = table
    tracker = TelemetryTracker(db=db)

    result = tracker.track_universe_snapshot_rows(
        snapshot_id="farm-1",
        rows=[
            {
                "symbol": "BTC/USDT",
                "asset_class": "crypto",
                "rank": 1,
                "source": "radar_scan",
                "volume": 12345,
            }
        ],
    )

    assert result["ok"] is True
    db.table.assert_called_with("universe_snapshot")
    assert table.insert.called
