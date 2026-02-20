from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

from src.api.server import (
    SummaryDTO,
    _derive_bot_status,
    create_app,
)
from src.api.candidates import build_candidate_capability_matrix, scan_non_crypto_candidates


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


def test_candidates_insights_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr("src.api.server.get_db", lambda: object())
    monkeypatch.setattr("src.api.server._resolve_mode", lambda db, mode: "LIVE")
    monkeypatch.setattr(
        "src.api.server.compute_candidate_insights",
        lambda db, mode, limit, log_limit: {
            "mode": mode,
            "primary_source": "fundamental_coins",
            "source_counts": {"fundamental_coins_total": 3, "assets_active_total": 2},
            "total_candidates_raw": 3,
            "total_candidates_visible": 1,
            "why_limited_note": "Candidate list currently follows fundamental_coins table.",
            "latest_scan": None,
            "candidate_types": [],
            "capabilities": [],
            "agents": [],
            "scanner_logs": [],
            "candidates": [],
        },
    )

    response = client.get("/api/candidates/insights", params={"mode": "LIVE", "limit": 80, "log_limit": 20})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["mode"] == "LIVE"
    assert body["data"]["total_candidates_visible"] == 1


def test_candidates_scan_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr("src.api.server.get_db", lambda: object())
    monkeypatch.setattr("src.api.server._resolve_mode", lambda db, mode: "PAPER")
    monkeypatch.setattr("src.api.server._get_price_spy", lambda: object())
    monkeypatch.setattr(
        "src.api.server.run_manual_candidate_scan",
        lambda db, spy, mode, limit, include_non_crypto, deep_scan, actor: {
            "scan_run_id": 101,
            "status": "COMPLETED",
            "mode": mode,
            "actor": actor,
            "scanned_total": 25,
            "qualified_total": 9,
            "qualified_symbols": ["BTC/USDT", "AAPL", "XAUUSD=X"],
            "counts_by_type": {"crypto": 6, "stock": 2, "gold": 1, "silver": 0, "other": 0},
            "sources": {"crypto_radar": 20, "non_crypto_api": 5},
            "include_non_crypto": include_non_crypto,
            "deep_scan": deep_scan,
            "message": "ok",
        },
    )

    response = client.post(
        "/api/candidates/scan",
        params={"mode": "PAPER", "limit": 60, "include_non_crypto": True, "deep_scan": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "COMPLETED"
    assert body["data"]["qualified_total"] == 9


def test_candidate_capability_matrix_honors_custom_connectors(monkeypatch):
    monkeypatch.setenv("BINANCE_API_KEY", "key")
    monkeypatch.setenv("BINANCE_SECRET", "secret")
    monkeypatch.setenv("STOCK_API_NAME", "Alpaca")
    monkeypatch.setenv("STOCK_API_URL", "https://api.alpaca.markets")
    monkeypatch.setenv("GOLD_API_NAME", "MetalsAPI")
    monkeypatch.setenv("GOLD_API_URL", "https://metals.example.com")
    monkeypatch.delenv("SILVER_API_NAME", raising=False)
    monkeypatch.delenv("SILVER_API_URL", raising=False)
    monkeypatch.delenv("SILVER_API_KEY", raising=False)

    rows = build_candidate_capability_matrix()
    lookup = {row["market_type"]: row for row in rows}

    assert lookup["crypto"]["live_enabled"] is True
    assert lookup["stock"]["live_enabled"] is True
    assert lookup["gold"]["live_enabled"] is True
    assert lookup["silver"]["live_enabled"] is False
    assert lookup["silver"]["api_name"] == "Yahoo Finance (scan only)"


def test_non_crypto_scan_preview_available_without_external_api(monkeypatch):
    monkeypatch.setenv("STOCK_SCAN_SYMBOLS", "AAPL,MSFT")
    monkeypatch.setenv("GOLD_SCAN_SYMBOLS", "XAUUSD=X")
    monkeypatch.setenv("SILVER_SCAN_SYMBOLS", "XAGUSD=X")

    rows = scan_non_crypto_candidates(limit_per_type=2, use_quote_api=False)
    assert len(rows) >= 4

    by_type = {}
    for row in rows:
        by_type.setdefault(row["candidate_type"], 0)
        by_type[row["candidate_type"]] += 1

    assert by_type["stock"] >= 2
    assert by_type["gold"] >= 1
    assert by_type["silver"] >= 1
    assert all(int(row.get("manual_score", 0)) >= 5 for row in rows)


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


def test_control_state_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())
    monkeypatch.setattr(
        "src.api.server._get_control_state_payload",
        lambda db: {
            "trading_mode": "PAPER",
            "bot_status": "ACTIVE",
            "bot_status_detail": "ok",
            "heartbeat_age_sec": 4,
            "last_heartbeat_at": "2026-02-19T00:00:00+00:00",
            "uptime_sec": 1800,
            "latest_update_on": "2026-02-19T00:00:01+00:00",
        },
    )

    response = client.get("/api/control/state")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["trading_mode"] == "PAPER"
    assert body["data"]["bot_status"] == "ACTIVE"


def test_control_action_sets_status_and_returns_payload(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    captured = {}

    def fake_set_bot_status(db, status_value, detail=None):
        captured["status"] = status_value
        captured["detail"] = detail
        return status_value

    monkeypatch.setattr("src.api.server._set_bot_status", fake_set_bot_status)
    monkeypatch.setattr(
        "src.api.server._get_control_state_payload",
        lambda db: {
            "trading_mode": "PAPER",
            "bot_status": captured.get("status", "UNKNOWN"),
            "bot_status_detail": captured.get("detail"),
        },
    )

    response = client.post("/api/control/action", params={"action": "pause", "actor": "tester"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert captured["status"] == "PAUSED"
    assert "tester" in captured["detail"]
    assert body["data"]["bot_status"] == "PAUSED"


def test_control_mode_requires_confirm_live(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    response = client.post("/api/control/mode", params={"mode": "LIVE", "confirm_live": "false"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "E_VALIDATION_400"


def test_control_mode_switches_and_sets_status_detail(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    calls = {"mode": None, "upserts": []}

    def fake_set_trading_mode(db, mode_value):
        calls["mode"] = mode_value
        return "LIVE"

    def fake_upsert(db, key, value):
        calls["upserts"].append((key, value))

    monkeypatch.setattr("src.api.server._set_trading_mode", fake_set_trading_mode)
    monkeypatch.setattr("src.api.server._upsert_bot_config_value", fake_upsert)
    monkeypatch.setattr(
        "src.api.server._get_control_state_payload",
        lambda db: {"trading_mode": "LIVE", "bot_status": "ACTIVE", "bot_status_detail": "ok"},
    )

    response = client.post("/api/control/mode", params={"mode": "LIVE", "confirm_live": "true", "actor": "tester"})
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert calls["mode"] == "LIVE"
    assert calls["upserts"]
    key, value = calls["upserts"][0]
    assert key == "BOT_STATUS_DETAIL"
    assert "LIVE" in value
