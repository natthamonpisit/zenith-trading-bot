from fastapi.testclient import TestClient

from src.api.server import create_app


def test_replay_score_decomposition_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    class DummyTracker:
        def __init__(self, db):
            self.db = db

        def get_signal_scores(self, symbol=None, run_id=None, timeframe=None, limit=50):
            return [
                {
                    "id": "s-1",
                    "run_id": run_id or "run-1",
                    "symbol": symbol or "BTC/USDT",
                    "timeframe": timeframe or "1h",
                    "total_score": 75.0,
                    "threshold": 60.0,
                    "passed_threshold": True,
                    "component_scores": {"trend": 80.0, "momentum": 72.0},
                    "weighted_scores": {"trend": 22.0, "momentum": 16.0},
                    "weights": {"trend": 25.0, "momentum": 20.0},
                    "notes": ["market_trend=UPTREND"],
                    "created_at": "2026-02-20T10:00:00+00:00",
                }
            ]

    monkeypatch.setattr("src.api.server.TelemetryTracker", DummyTracker)

    response = client.get("/api/replay/score-decomposition", params={"symbol": "BTC/USDT", "run_id": "run-1"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"][0]["symbol"] == "BTC/USDT"
    assert body["data"][0]["components"][0]["component"] == "trend"


def test_replay_decision_reasons_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    class DummyTracker:
        def __init__(self, db):
            self.db = db

        def get_ai_decisions(self, symbol=None, run_id=None, limit=50):
            return [{"id": "a1", "symbol": symbol or "BTC/USDT", "run_id": run_id or "run-1"}]

        def get_rule_evaluations(self, symbol=None, run_id=None, limit=50):
            return [{"id": "r1", "symbol": symbol or "BTC/USDT", "run_id": run_id or "run-1"}]

        def get_signal_scores(self, symbol=None, run_id=None, limit=50):
            return [
                {
                    "id": "s1",
                    "symbol": symbol or "BTC/USDT",
                    "run_id": run_id or "run-1",
                    "total_score": 74.5,
                    "threshold": 60.0,
                    "passed_threshold": True,
                    "notes": ["ok"],
                    "created_at": "2026-02-20T10:00:00+00:00",
                }
            ]

        def get_tuning_proposal_validations(self, tuning_proposal_id=None, limit=50):
            return [{"id": "v1", "tuning_proposal_id": tuning_proposal_id, "passed": True}]

    monkeypatch.setattr("src.api.server.TelemetryTracker", DummyTracker)
    proposal_id = "44444444-4444-4444-4444-444444444444"
    response = client.get(
        "/api/replay/decision-reasons",
        params={"symbol": "BTC/USDT", "run_id": "run-1", "tuning_proposal_id": proposal_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["ai_decisions"][0]["id"] == "a1"
    assert body["data"]["rule_evaluations"][0]["id"] == "r1"
    assert body["data"]["score_notes"][0]["id"] == "s1"
    assert body["data"]["tuning_validations"][0]["id"] == "v1"


def test_replay_phase3_metrics_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr(
        "src.api.server.snapshot_metrics",
        lambda: {"counters": {"phase3_query_error_count": 0}, "durations_ms": {"phase3_run_duration_ms": {"count": 1}}},
    )

    response = client.get("/api/replay/phase3-metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "counters" in body["data"]
    assert "durations_ms" in body["data"]
