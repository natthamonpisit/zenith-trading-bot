from types import SimpleNamespace

import pytest

from src.api.candidates import (
    _persist_universe_snapshot_rows,
    build_candidate_agent_map,
    compute_candidate_insights,
)


class _FakeQuery:
    def __init__(self, db, table_name):
        self._db = db
        self._table_name = table_name
        self._eq_filters = {}
        self._in_filters = {}
        self._order_field = None
        self._order_desc = False
        self._limit = None
        self._count = None

    def select(self, _fields="*", count=None):
        self._count = count
        return self

    def eq(self, key, value):
        self._eq_filters[key] = value
        return self

    def in_(self, key, values):
        self._in_filters[key] = set(values)
        return self

    def order(self, field, desc=False):
        self._order_field = field
        self._order_desc = bool(desc)
        return self

    def limit(self, value):
        self._limit = int(value)
        return self

    def execute(self):
        rows = list(self._db.rows.get(self._table_name, []))

        for key, value in self._eq_filters.items():
            rows = [row for row in rows if row.get(key) == value]
        for key, values in self._in_filters.items():
            rows = [row for row in rows if row.get(key) in values]

        if self._count == "exact":
            return SimpleNamespace(data=[], count=len(rows))

        if self._order_field:
            rows = sorted(rows, key=lambda row: row.get(self._order_field) or 0, reverse=self._order_desc)
        if self._limit is not None:
            rows = rows[: self._limit]

        return SimpleNamespace(data=rows, count=None)


class _FakeDB:
    def __init__(self, rows):
        self.rows = rows

    def table(self, table_name):
        return _FakeQuery(self, table_name)


class _InsertCaptureQuery:
    def __init__(self, db, table_name):
        self._db = db
        self._table_name = table_name
        self._action = None
        self._payload = None

    def insert(self, payload):
        self._action = "insert"
        self._payload = payload
        return self

    def upsert(self, payload):
        self._action = "upsert"
        self._payload = payload
        return self

    def execute(self):
        if self._table_name == "universe_snapshot" and self._action == "insert":
            raise RuntimeError("relation universe_snapshot does not exist")
        self._db.calls.append(
            {
                "table": self._table_name,
                "action": self._action,
                "payload": self._payload,
            }
        )
        return SimpleNamespace(data=[])


class _InsertCaptureDB:
    def __init__(self):
        self.calls = []

    def table(self, table_name):
        return _InsertCaptureQuery(self, table_name)


@pytest.mark.unit
def test_build_candidate_agent_map_prefers_ai_model_from_config():
    db = _FakeDB(
        rows={
            "bot_config": [
                {"key": "AI_MODEL", "value": "MINIMAX_PROD:custom-v2"},
            ]
        }
    )

    rows = build_candidate_agent_map(db)
    strategist = next(row for row in rows if row["agent_id"] == "strategist")
    assert strategist["agent_type"] == "AI"
    assert strategist["model_or_engine"] == "MINIMAX_PROD:custom-v2"


@pytest.mark.unit
def test_compute_candidate_insights_paper_includes_multi_asset_preview(monkeypatch):
    db = _FakeDB(
        rows={
            "bot_config": [{"key": "TRADING_UNIVERSE", "value": "ALL"}],
            "fundamental_coins": [
                {"symbol": "BTC/USDT", "status": "WHITELIST", "manual_score": 9, "notes": "core", "updated_at": None},
                {"symbol": "ETH/USDT", "status": "NEUTRAL", "manual_score": 7, "notes": "", "updated_at": None},
            ],
            "assets": [
                {"symbol": "BTC/USDT", "market_type": "crypto", "status": "active", "tags": []},
                {"symbol": "ETH/USDT", "market_type": "crypto", "status": "active", "tags": []},
            ],
            "farming_history": [],
            "system_logs": [],
        }
    )

    monkeypatch.setattr(
        "src.api.candidates.scan_non_crypto_candidates",
        lambda limit_per_type=10, use_quote_api=False: [
            {"symbol": "AAPL", "status": "WHITELIST", "manual_score": 8, "notes": "preview", "candidate_type": "stock"},
            {"symbol": "XAUUSD=X", "status": "NEUTRAL", "manual_score": 6, "notes": "preview", "candidate_type": "gold"},
        ],
    )
    monkeypatch.setattr(
        "src.api.candidates.build_candidate_capability_matrix",
        lambda: [
            {"market_type": "crypto", "live_enabled": True},
            {"market_type": "stock", "live_enabled": False},
            {"market_type": "gold", "live_enabled": False},
            {"market_type": "silver", "live_enabled": False},
        ],
    )

    payload = compute_candidate_insights(db, mode="PAPER", limit=20, log_limit=10)

    assert payload["mode"] == "PAPER"
    assert payload["primary_source"].endswith("paper_preview")
    assert payload["total_candidates_raw"] >= 3
    assert payload["total_candidates_visible"] >= 3
    assert payload["why_limited_note"] is not None
    assert any(row["candidate_type"] == "stock" for row in payload["candidates"])
    assert any(row["candidate_type"] == "gold" for row in payload["candidates"])


@pytest.mark.unit
def test_compute_candidate_insights_live_filters_to_live_tradable_and_whitelist(monkeypatch):
    db = _FakeDB(
        rows={
            "bot_config": [
                {"key": "TRADING_UNIVERSE", "value": "SAFE_LIST"},
            ],
            "fundamental_coins": [
                {"symbol": "BTC/USDT", "status": "NEUTRAL", "manual_score": 9, "notes": "", "updated_at": None},
                {"symbol": "SOL/USDT", "status": "WHITELIST", "manual_score": 8, "notes": "", "updated_at": None},
            ],
            "assets": [
                {"symbol": "BTC/USDT", "market_type": "crypto", "status": "active", "tags": []},
                {"symbol": "SOL/USDT", "market_type": "crypto", "status": "active", "tags": []},
            ],
            "farming_history": [
                {
                    "id": 17,
                    "start_time": "2026-02-19T10:00:00+00:00",
                    "end_time": "2026-02-19T10:00:05+00:00",
                    "status": "COMPLETED",
                    "candidates_found": 1,
                    "logs": "scan universe=10 passed=1",
                    "created_at": "2026-02-19T10:00:05+00:00",
                }
            ],
            "system_logs": [
                {"id": 1, "level": "INFO", "role": "Radar", "message": "scan completed", "created_at": "2026-02-19T10:00:05+00:00"},
                {"id": 2, "level": "INFO", "role": "Judge", "message": "position opened", "created_at": "2026-02-19T10:00:06+00:00"},
            ],
        }
    )

    monkeypatch.setattr(
        "src.api.candidates.build_candidate_capability_matrix",
        lambda: [
            {"market_type": "crypto", "live_enabled": True},
            {"market_type": "stock", "live_enabled": False},
            {"market_type": "gold", "live_enabled": False},
            {"market_type": "silver", "live_enabled": False},
        ],
    )

    payload = compute_candidate_insights(db, mode="LIVE", limit=20, log_limit=10)

    assert payload["mode"] == "LIVE"
    assert payload["total_candidates_raw"] == 2
    assert payload["total_candidates_visible"] == 1
    assert [row["symbol"] for row in payload["candidates"]] == ["SOL/USDT"]
    assert payload["latest_scan"]["scan_run_id"] == "17"
    assert payload["latest_scan"]["reject_count"] == 9
    assert len(payload["scanner_logs"]) == 1
    assert payload["scanner_logs"][0]["role"] == "Radar"


@pytest.mark.unit
def test_universe_snapshot_persist_soft_fails_when_table_missing():
    db = _InsertCaptureDB()
    rows = [
        {
            "symbol": "BTC/USDT",
            "candidate_type": "crypto",
            "status": "WHITELIST",
            "source": "radar_crypto",
            "volume": 123456.0,
        }
    ]

    _persist_universe_snapshot_rows(
        db=db,
        snapshot_id="manual-scan-99",
        rows=rows,
        mode="PAPER",
        actor="test",
        stage="manual_candidate_scan",
    )

    # Should not raise, and should log warning through system_logs fallback.
    assert any(call["table"] == "system_logs" and call["action"] == "insert" for call in db.calls)
