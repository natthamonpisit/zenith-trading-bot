from datetime import datetime, timedelta, timezone

import pytest

from src.roles.walk_forward import WalkForwardEngine, build_walk_forward_folds


def _rows(count: int, start: datetime):
    rows = []
    for i in range(count):
        rows.append(
            {
                "id": f"pt-{i}",
                "pnl": (-1.0 if i % 3 == 0 else 1.8) * (1 + (i % 5) * 0.1),
                "created_at": (start + timedelta(hours=i)).isoformat(),
            }
        )
    return rows


class _FakeTracker:
    def __init__(self):
        self.seed_status = None
        self.updated_status = None
        self.fold_rows = []

    def track_walk_forward_run(self, **kwargs):
        self.seed_status = kwargs.get("status")
        return {"ok": True, "row": {"id": "wf-run-1"}}

    def update_walk_forward_run(self, **kwargs):
        self.updated_status = kwargs.get("status")
        return {"ok": True, "row": {"id": kwargs.get("walk_forward_run_id")}}

    def track_walk_forward_fold_results(self, **kwargs):
        self.fold_rows = kwargs.get("fold_rows") or []
        return {"ok": True, "rows": self.fold_rows}


@pytest.mark.unit
def test_build_walk_forward_folds_has_strict_time_order():
    rows = _rows(120, datetime(2026, 1, 1, tzinfo=timezone.utc))
    folds = build_walk_forward_folds(rows, fold_count=5, min_train_size=30, min_test_size=10)

    assert len(folds) >= 3
    for fold in folds:
        assert fold.train_rows
        assert fold.test_rows
        assert fold.train_to < fold.test_from


@pytest.mark.unit
def test_build_walk_forward_folds_raises_on_same_timestamp_leakage():
    rows = _rows(60, datetime(2026, 1, 1, tzinfo=timezone.utc))
    for row in rows:
        row["created_at"] = "2026-01-01T00:00:00+00:00"

    with pytest.raises(ValueError):
        build_walk_forward_folds(rows, fold_count=3, min_train_size=20, min_test_size=10)


@pytest.mark.unit
def test_walk_forward_run_validation_persists_folds_and_summary(monkeypatch):
    tracker = _FakeTracker()
    engine = WalkForwardEngine(db=None, tracker=tracker)

    monkeypatch.setattr(
        engine,
        "_fetch_post_trade_rows",
        lambda run_id=None, limit=3000: _rows(140, datetime(2026, 1, 1, tzinfo=timezone.utc)),
    )

    result = engine.run_validation(
        run_id="run-1",
        timeframe="1h",
        fold_count=4,
        min_sample_size=50,
        min_train_size=30,
        min_test_size=10,
        row_limit=4000,
    )

    assert result["ok"] is True
    assert result["walk_forward_run_id"] == "wf-run-1"
    assert result["summary"]["fold_count"] >= 1
    assert tracker.seed_status == "RUNNING"
    assert tracker.updated_status == "COMPLETED"
    assert len(tracker.fold_rows) >= 1
