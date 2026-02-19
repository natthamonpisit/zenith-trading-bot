from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

from src.api.server import SummaryDTO, _derive_bot_status, create_app


def test_health_envelope(monkeypatch):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr("src.api.server.get_db", lambda: object())
    monkeypatch.setattr("src.api.server._probe_db_health", lambda db: True)

    response = client.get("/api/health")
    assert response.status_code == 200

    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
    assert body["meta"]["version"] == "v1"


def test_dashboard_summary_uses_contract(monkeypatch):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr("src.api.server.get_db", lambda: object())
    monkeypatch.setattr("src.api.server._resolve_mode", lambda db, mode: "PAPER")
    monkeypatch.setattr(
        "src.api.server._compute_summary",
        lambda db, mode: SummaryDTO(
            equity=1000.0,
            daily_pnl=12.5,
            drawdown_pct=1.2,
            open_positions=2,
            win_rate=66.7,
            bot_status="ACTIVE",
        ),
    )

    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["equity"] == 1000.0
    assert body["data"]["bot_status"] == "ACTIVE"


def test_derive_bot_status_prefers_explicit_status(monkeypatch):
    def fake_fetch(db, key):
        if key == "BOT_STATUS":
            return "STOPPED"
        return None

    monkeypatch.setattr("src.api.server._fetch_bot_config_value", fake_fetch)
    assert _derive_bot_status(object(), "PAPER") == "STOPPED"


def test_derive_bot_status_falls_back_to_active_on_fresh_heartbeat(monkeypatch):
    monkeypatch.setattr("src.api.server._fetch_bot_config_value", lambda db, key: None)
    monkeypatch.setattr("src.api.server._get_heartbeat_age_seconds", lambda db: 8)
    monkeypatch.setattr("src.api.server._has_active_session", lambda db, mode: False)
    assert _derive_bot_status(object(), "PAPER") == "ACTIVE"


def test_derive_bot_status_falls_back_to_degraded_for_active_session_without_heartbeat(monkeypatch):
    monkeypatch.setattr("src.api.server._fetch_bot_config_value", lambda db, key: None)
    monkeypatch.setattr("src.api.server._get_heartbeat_age_seconds", lambda db: None)
    monkeypatch.setattr("src.api.server._has_active_session", lambda db, mode: True)
    assert _derive_bot_status(object(), "PAPER") == "DEGRADED"


def test_performance_review_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr("src.api.server.get_db", lambda: object())
    monkeypatch.setattr("src.api.server._resolve_mode", lambda db, mode: "PAPER")

    class DummyStrategist:
        def analyze_performance_overview(self, days_range, is_sim, min_trades, include_ai):
            return {
                "mode": "PAPER",
                "period_days": days_range,
                "minimum_trades": min_trades,
                "sample_ready": True,
                "deterministic": {"total_trades": 42, "win_rate": 61.9},
                "ai_model": "MINIMAX_CODING:MiniMax-M2.5",
                "ai_report": "## Review\\n- good",
                "skip_reason": None,
            }

    monkeypatch.setattr("src.api.server._get_strategist", lambda: DummyStrategist())
    response = client.get("/api/performance/review", params={"days": 7, "min_trades": 20, "include_ai": True})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["period_days"] == 7
    assert body["data"]["deterministic"]["total_trades"] == 42
    assert body["data"]["ai_model"] == "MINIMAX_CODING:MiniMax-M2.5"


def test_klines_invalid_timeframe_returns_validation_error():
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/klines", params={"symbol": "BTC/USDT", "tf": "2m", "limit": 20})
    assert response.status_code == 400

    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "E_VALIDATION_400"


def test_klines_cache_path(monkeypatch):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr("src.api.server.get_db", lambda: object())
    monkeypatch.setattr(
        "src.api.server._fetch_cached_klines",
        lambda db, symbol, tf, limit: [
            {"ts_open": "2026-02-18T10:00:00+00:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 10.0},
            {"ts_open": "2026-02-18T11:00:00+00:00", "open": 100.5, "high": 102.0, "low": 100.2, "close": 101.8, "volume": 12.0},
        ],
    )
    monkeypatch.setattr(
        "src.api.server._fetch_exchange_klines",
        lambda symbol, tf, limit: [],
    )

    response = client.get("/api/klines", params={"symbol": "BTC/USDT", "tf": "1h", "limit": 2})
    assert response.status_code == 200

    body = response.json()
    assert body["success"] is True
    assert body["data"]["symbol"] == "BTC/USDT"
    assert body["data"]["tf"] == "1h"
    assert len(body["data"]["candles"]) == 2


def test_read_token_auth_middleware(monkeypatch):
    monkeypatch.setenv("API_READ_TOKEN", "secret-token")

    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr("src.api.server.get_db", lambda: object())
    monkeypatch.setattr("src.api.server._resolve_mode", lambda db, mode: "PAPER")
    monkeypatch.setattr(
        "src.api.server._compute_summary",
        lambda db, mode: SummaryDTO(
            equity=1000.0,
            daily_pnl=0.0,
            drawdown_pct=0.0,
            open_positions=0,
            win_rate=0.0,
            bot_status="ACTIVE",
        ),
    )

    unauthorized = client.get("/api/dashboard/summary")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == "E_AUTH_401"

    authorized = client.get("/api/dashboard/summary", headers={"X-API-Key": "secret-token"})
    assert authorized.status_code == 200
    assert authorized.json()["success"] is True


def test_events_endpoint_envelope(monkeypatch):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr("src.api.server.get_db", lambda: object())
    monkeypatch.setattr(
        "src.api.server._compute_events",
        lambda db, limit: [
            {"id": "1", "level": "INFO", "role": "Judge", "message": "ok", "created_at": "2026-02-18T00:00:00Z"}
        ],
    )

    response = client.get("/api/events", params={"limit": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"][0]["role"] == "Judge"


def test_cors_allows_localhost_3000_in_dev(monkeypatch):
    monkeypatch.setenv("API_CORS_ORIGINS", "http://localhost:5173")
    app = create_app()
    client = TestClient(app)

    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_ws_dashboard_topic_once(monkeypatch):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr("src.api.server.get_db", lambda: object())
    monkeypatch.setattr(
        "src.api.server._resolve_ws_payload",
        lambda topic, db, mode: ("dashboard.summary", {"mode": "PAPER", "summary": {"equity": 1000}}),
    )

    with client.websocket_connect("/ws?topic=dashboard.summary&once=true") as ws:
        event = ws.receive_json()
        assert event["event_type"] == "dashboard.summary"
        assert event["payload"]["summary"]["equity"] == 1000


def test_ws_invalid_topic_returns_error_and_closes(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    with client.websocket_connect("/ws?topic=invalid.topic&once=true") as ws:
        event = ws.receive_json()
        assert event["event_type"] == "system.error"
        assert event["payload"]["code"] == "E_VALIDATION_400"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
        assert exc_info.value.code == 1008


def test_ws_token_auth(monkeypatch):
    monkeypatch.setenv("API_READ_TOKEN", "secret-token")
    app = create_app()
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws?topic=dashboard.summary&once=true"):
            pass
    assert exc_info.value.code == 1008


def test_positions_session_filter_pass_through(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    captured = {}

    def fake_compute_positions(db, is_open, symbol_filter, session_id_filter, limit):
        captured["session_id"] = session_id_filter
        return []

    monkeypatch.setattr("src.api.server._compute_positions", fake_compute_positions)

    valid_session_id = "11111111-1111-1111-1111-111111111111"
    response = client.get("/api/positions", params={"session_id": valid_session_id, "limit": 5})
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert captured["session_id"] == valid_session_id


def test_positions_invalid_session_id(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    response = client.get("/api/positions", params={"session_id": "not-a-uuid"})
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "E_VALIDATION_400"


def test_replay_ai_decisions_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    class DummyTracker:
        def __init__(self, db):
            self.db = db

        def get_ai_decisions(self, symbol=None, run_id=None, tier=None, limit=100):
            return [{"id": "a1", "symbol": symbol or "BTC/USDT", "tier": tier or "TIER_2_DECISION"}]

    monkeypatch.setattr("src.api.server.TelemetryTracker", DummyTracker)
    run_id = "11111111-1111-1111-1111-111111111111"
    response = client.get("/api/replay/ai-decisions", params={"run_id": run_id, "symbol": "BTC/USDT", "tier": "TIER_2_DECISION"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"][0]["id"] == "a1"


def test_replay_bundle_invalid_run_id(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())
    response = client.get("/api/replay/bundle", params={"run_id": "bad-id"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "E_VALIDATION_400"


def test_hardening_health_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    class DummyHardening:
        def __init__(self, db):
            self.db = db

        def get_health_snapshot(self):
            return {"dual_run_mode": "ENABLED", "alerts": [], "heartbeat_age_sec": 5}

    monkeypatch.setattr("src.api.server.HardeningService", DummyHardening)
    response = client.get("/api/ops/hardening/health")
    assert response.status_code == 200
    assert response.json()["data"]["dual_run_mode"] == "ENABLED"


def test_cutover_apply_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    class DummyCutover:
        def __init__(self, db):
            self.db = db

        def get_status(self):
            return {
                "primary_dashboard": "STREAMLIT",
                "streamlit_fallback_enabled": True,
                "dual_run_mode": "ENABLED",
                "cutover_completed_at": None,
                "cutover_ready": False,
            }

        def apply_cutover(self, primary_dashboard, fallback_enabled, actor):
            return {
                "primary_dashboard": primary_dashboard.upper(),
                "streamlit_fallback_enabled": fallback_enabled,
                "dual_run_mode": "ENABLED",
                "cutover_completed_at": "2026-02-18T00:00:00Z",
                "cutover_ready": True,
            }

    monkeypatch.setattr("src.api.server.CutoverService", DummyCutover)
    response = client.post("/api/cutover/apply", params={"primary_dashboard": "REACT", "streamlit_fallback_enabled": "true", "actor": "tester"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["primary_dashboard"] == "REACT"


def test_cutover_apply_validation_error(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    class DummyCutover:
        def __init__(self, db):
            self.db = db

        def apply_cutover(self, primary_dashboard, fallback_enabled, actor):
            raise ValueError("primary_dashboard must be REACT or STREAMLIT")

    monkeypatch.setattr("src.api.server.CutoverService", DummyCutover)
    response = client.post("/api/cutover/apply", params={"primary_dashboard": "BAD"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "E_VALIDATION_400"
