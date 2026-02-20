from types import SimpleNamespace

import pytest

from src.roles.tuning_advisor import TuningAdvisor


class _FakeDBQuery:
    def __init__(self, db, table_name):
        self._db = db
        self._table = table_name
        self._payload = None
        self._eq_filters = {}

    def select(self, *_args):
        return self

    def eq(self, key, value):
        self._eq_filters[key] = value
        return self

    def limit(self, _value):
        return self

    def upsert(self, payload):
        self._payload = payload
        return self

    def execute(self):
        if self._table == "bot_config" and self._payload is not None:
            self._db.upserts.append(self._payload)
            return SimpleNamespace(data=[self._payload])
        if self._table == "bot_config":
            return SimpleNamespace(data=self._db.bot_config_rows)
        return SimpleNamespace(data=[])


class _FakeDB:
    def __init__(self):
        self.upserts = []
        self.bot_config_rows = [
            {"key": "PHASE3_MIN_SAMPLE_SIZE", "value": "50"},
            {"key": "PHASE3_MAX_ALLOWED_DRAWDOWN", "value": "20"},
            {"key": "MIN_TOTAL_SCORE_TO_CANDIDATE", "value": "60"},
            {"key": "SCORE_WEIGHT_TREND", "value": "25"},
            {"key": "SCORE_WEIGHT_MOMENTUM", "value": "20"},
            {"key": "SCORE_WEIGHT_VOLATILITY", "value": "15"},
            {"key": "SCORE_WEIGHT_LIQUIDITY", "value": "20"},
            {"key": "SCORE_WEIGHT_STRUCTURE", "value": "10"},
            {"key": "SCORE_WEIGHT_PORTFOLIO", "value": "10"},
        ]

    def table(self, table_name):
        return _FakeDBQuery(self, table_name)


class _FakeTracker:
    def __init__(self, run_row=None, proposal_row=None):
        self.run_row = run_row
        self.proposal_row = proposal_row or {
            "id": "tp-1",
            "status": "DRAFT",
            "proposal_payload": {"proposed_updates": {}},
        }
        self.saved_validations = []
        self.updated_status = None

    def get_walk_forward_run_by_id(self, run_id):
        return self.run_row if self.run_row and self.run_row.get("id") == run_id else None

    def track_tuning_proposal(self, **kwargs):
        payload = dict(kwargs)
        payload["id"] = "tp-1"
        self.proposal_row = payload
        return {"ok": True, "row": {"id": "tp-1"}}

    def track_tuning_proposal_validation(self, **kwargs):
        self.saved_validations.append(kwargs)
        return {"ok": True}

    def update_tuning_proposal(self, **kwargs):
        self.updated_status = kwargs.get("status")
        self.proposal_row["status"] = kwargs.get("status", self.proposal_row.get("status"))
        return {"ok": True}

    def get_tuning_proposal_by_id(self, proposal_id):
        if proposal_id != "tp-1":
            return None
        return self.proposal_row


@pytest.mark.unit
def test_create_proposal_for_run_rejects_low_sample_size():
    db = _FakeDB()
    tracker = _FakeTracker(
        run_row={
            "id": "wf-1",
            "sample_size": 20,
            "metrics_json": {"win_rate": 40, "expectancy": -0.2, "max_drawdown_pct": 12.5},
        }
    )
    advisor = TuningAdvisor(db=db, tracker=tracker)

    payload = advisor.create_proposal_for_walk_forward_run("wf-1")

    assert payload["ok"] is True
    assert payload["status"] == "REJECTED"
    assert any(v.get("rule_code") == "MIN_SAMPLE_SIZE" for v in payload["validations"])
    assert tracker.updated_status == "REJECTED"


@pytest.mark.unit
def test_transition_status_blocks_invalid_path():
    db = _FakeDB()
    tracker = _FakeTracker(proposal_row={"id": "tp-1", "status": "DRAFT", "proposal_payload": {"proposed_updates": {}}})
    advisor = TuningAdvisor(db=db, tracker=tracker)

    payload = advisor.transition_proposal_status("tp-1", "APPLIED", actor="tester")

    assert payload["ok"] is False
    assert payload["error"] == "invalid_status_transition"


@pytest.mark.unit
def test_apply_requires_manual_approval():
    db = _FakeDB()
    tracker = _FakeTracker(
        proposal_row={
            "id": "tp-1",
            "status": "VALIDATED",
            "proposal_payload": {"proposed_updates": {"MIN_TOTAL_SCORE_TO_CANDIDATE": 62}},
        }
    )
    advisor = TuningAdvisor(db=db, tracker=tracker)

    payload = advisor.apply_proposal("tp-1", actor="tester", dry_run=False)

    assert payload["ok"] is False
    assert payload["error"] == "proposal_not_manually_approved"


@pytest.mark.unit
def test_apply_after_manual_approval_updates_config():
    db = _FakeDB()
    tracker = _FakeTracker(
        proposal_row={
            "id": "tp-1",
            "status": "APPROVED_MANUAL",
            "proposal_payload": {
                "proposed_updates": {
                    "MIN_TOTAL_SCORE_TO_CANDIDATE": 63,
                    "SCORE_WEIGHT_TREND": 28,
                }
            },
        }
    )
    advisor = TuningAdvisor(db=db, tracker=tracker)

    payload = advisor.apply_proposal("tp-1", actor="tester", dry_run=False)

    assert payload["ok"] is True
    assert payload["status"] == "APPLIED"
    assert "MIN_TOTAL_SCORE_TO_CANDIDATE" in payload["applied_keys"]
    assert "SCORE_WEIGHT_TREND" in payload["applied_keys"]
    assert len(db.upserts) == 2
