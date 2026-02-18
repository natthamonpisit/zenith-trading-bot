from datetime import datetime, timedelta, timezone

from src.ops.cutover import CutoverService
from src.ops.hardening import HardeningService, compare_dashboard_summary


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, db, name):
        self.db = db
        self.name = name
        self._eq_filters = {}
        self._limit = None

    def select(self, _fields):
        return self

    def eq(self, key, value):
        self._eq_filters[key] = value
        return self

    def limit(self, value):
        self._limit = value
        return self

    def order(self, _field, desc=False):
        self._order_desc = desc
        return self

    def upsert(self, payload):
        if self.name == "bot_config":
            key = payload["key"]
            self.db.config[key] = payload["value"]
        return self

    def insert(self, payload):
        if self.name == "audit_log":
            self.db.audit_rows.append(payload)
        return self

    def execute(self):
        if self.name == "bot_config":
            if "key" in self._eq_filters:
                key = self._eq_filters["key"]
                if key in self.db.config:
                    return FakeResult([{"key": key, "value": self.db.config[key]}])
                return FakeResult([])
            rows = [{"key": key, "value": value} for key, value in self.db.config.items()]
            return FakeResult(rows)

        if self.name == "system_logs":
            rows = list(self.db.logs)
            if self._limit is not None:
                rows = rows[: self._limit]
            return FakeResult(rows)

        return FakeResult([])


class FakeDB:
    def __init__(self):
        old = datetime.now(timezone.utc) - timedelta(seconds=400)
        self.config = {
            "DUAL_RUN_MODE": '"ENABLED"',
            "LAST_HEARTBEAT": str(old.timestamp()),
            "PRIMARY_DASHBOARD": '"STREAMLIT"',
            "STREAMLIT_FALLBACK_ENABLED": "true",
            "CUTOVER_COMPLETED_AT": "null",
        }
        self.logs = [
            {"id": "1", "level": "ERROR", "role": "System", "message": "x", "created_at": "2026-02-18T00:00:00Z"},
            {"id": "2", "level": "WARNING", "role": "System", "message": "y", "created_at": "2026-02-18T00:00:01Z"},
        ]
        self.audit_rows = []

    def table(self, name):
        return FakeTable(self, name)


def test_compare_dashboard_summary_detects_diff():
    primary = {"equity": 1000, "daily_pnl": 10, "drawdown_pct": 1, "open_positions": 2, "win_rate": 60}
    secondary = {"equity": 900, "daily_pnl": 10, "drawdown_pct": 1, "open_positions": 2, "win_rate": 60}
    report = compare_dashboard_summary(primary, secondary, tolerance_pct=2.0)
    assert report["parity_passed"] is False
    assert any(item["field"] == "equity" for item in report["differences"])


def test_hardening_service_alerts():
    db = FakeDB()
    service = HardeningService(db=db)
    snapshot = service.get_health_snapshot()
    assert snapshot["dual_run_mode"] == "ENABLED"
    assert snapshot["alerts"]
    assert any(alert["code"] == "HEARTBEAT_STALE" for alert in snapshot["alerts"])


def test_cutover_service_apply():
    db = FakeDB()
    service = CutoverService(db=db)
    before = service.get_status()
    assert before["primary_dashboard"] == "STREAMLIT"

    after = service.apply_cutover(primary_dashboard="REACT", fallback_enabled=True, actor="tester")
    assert after["primary_dashboard"] == "REACT"
    assert db.audit_rows
    assert db.audit_rows[0]["new_value"] == "REACT"
