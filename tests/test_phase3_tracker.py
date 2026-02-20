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


def test_track_walk_forward_run_insert():
    db = Mock()
    wf_table = _build_table_mock(execute_data=[{"id": "wf1"}])
    db.table.return_value = wf_table
    tracker = TelemetryTracker(db=db)

    result = tracker.track_walk_forward_run(
        run_id="run-1",
        phase3_run_key="wf-20260220-01",
        status="completed",
        timeframe="1h",
        dataset_scope="TOP_100",
        sample_size=120,
        fold_count=6,
        metrics_json={"win_rate": 0.58},
        params_json={"train_window": 180, "test_window": 30},
    )

    assert result["ok"] is True
    db.table.assert_called_with("walk_forward_runs")
    assert wf_table.insert.called
    insert_payload = wf_table.insert.call_args.args[0]
    assert insert_payload["status"] == "COMPLETED"
    assert insert_payload["sample_size"] == 120
    assert insert_payload["fold_count"] == 6


def test_track_walk_forward_fold_results_bulk_insert():
    db = Mock()
    fold_table = _build_table_mock(execute_data=[{"id": "fold1"}])
    db.table.return_value = fold_table
    tracker = TelemetryTracker(db=db)

    result = tracker.track_walk_forward_fold_results(
        walk_forward_run_id="11111111-1111-1111-1111-111111111111",
        fold_rows=[
            {
                "fold_index": 1,
                "sample_size": 40,
                "metrics_json": {"expectancy": 0.12},
            },
            {
                "fold_index": 2,
                "sample_size": 42,
                "metrics_json": {"expectancy": 0.10},
            },
        ],
    )

    assert result["ok"] is True
    db.table.assert_called_with("walk_forward_fold_results")
    assert fold_table.insert.called
    payload_rows = fold_table.insert.call_args.args[0]
    assert len(payload_rows) == 2
    assert payload_rows[0]["fold_index"] == 1
    assert payload_rows[1]["sample_size"] == 42


def test_get_tuning_proposals_with_filters():
    db = Mock()
    proposal_table = _build_table_mock(execute_data=[{"id": "tp1", "status": "VALIDATED"}])
    db.table.return_value = proposal_table
    tracker = TelemetryTracker(db=db)

    rows = tracker.get_tuning_proposals(
        walk_forward_run_id="22222222-2222-2222-2222-222222222222",
        status="VALIDATED",
        proposed_by="AI_ADVISOR",
        limit=25,
    )

    assert len(rows) == 1
    assert rows[0]["status"] == "VALIDATED"
    assert proposal_table.eq.call_count == 3


def test_replay_bundle_includes_phase3_sections():
    db = Mock()
    table = _build_table_mock(execute_data=[])
    db.table.return_value = table
    tracker = TelemetryTracker(db=db)

    bundle = tracker.get_replay_bundle("run-1", limit=5)

    assert "walk_forward_runs" in bundle
    assert "walk_forward_fold_results" in bundle
    assert "tuning_proposals" in bundle
    assert "tuning_proposal_validations" in bundle
