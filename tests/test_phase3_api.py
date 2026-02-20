from fastapi.testclient import TestClient

from src.api.server import create_app


def test_replay_walk_forward_runs_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    class DummyTracker:
        def __init__(self, db):
            self.db = db

        def get_walk_forward_runs(self, run_id=None, phase3_run_key=None, status=None, timeframe=None, limit=200):
            return [
                {
                    "id": "wf1",
                    "run_id": run_id or "run-1",
                    "phase3_run_key": phase3_run_key or "wf-20260220-01",
                    "status": status or "COMPLETED",
                    "timeframe": timeframe or "1h",
                }
            ]

    monkeypatch.setattr("src.api.server.TelemetryTracker", DummyTracker)

    response = client.get(
        "/api/replay/walk-forward-runs",
        params={"run_id": "run-1", "phase3_run_key": "wf-20260220-01", "status": "completed", "timeframe": "1h"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"][0]["id"] == "wf1"
    assert body["data"][0]["status"] == "COMPLETED"


def test_replay_walk_forward_folds_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    class DummyTracker:
        def __init__(self, db):
            self.db = db

        def get_walk_forward_fold_results(self, walk_forward_run_id=None, limit=500):
            return [{"id": "fold-1", "walk_forward_run_id": walk_forward_run_id, "fold_index": 1}]

    monkeypatch.setattr("src.api.server.TelemetryTracker", DummyTracker)
    run_uuid = "11111111-1111-1111-1111-111111111111"
    response = client.get("/api/replay/walk-forward-folds", params={"walk_forward_run_id": run_uuid, "limit": 10})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"][0]["walk_forward_run_id"] == run_uuid


def test_replay_walk_forward_folds_invalid_run_id(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())
    response = client.get("/api/replay/walk-forward-folds", params={"walk_forward_run_id": "not-a-uuid"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "E_VALIDATION_400"


def test_replay_tuning_proposals_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    class DummyTracker:
        def __init__(self, db):
            self.db = db

        def get_tuning_proposals(self, walk_forward_run_id=None, status=None, proposed_by=None, limit=200):
            return [
                {
                    "id": "tp1",
                    "walk_forward_run_id": walk_forward_run_id,
                    "status": status or "VALIDATED",
                    "proposed_by": proposed_by or "AI_ADVISOR",
                }
            ]

    monkeypatch.setattr("src.api.server.TelemetryTracker", DummyTracker)
    run_uuid = "22222222-2222-2222-2222-222222222222"
    response = client.get(
        "/api/replay/tuning-proposals",
        params={"walk_forward_run_id": run_uuid, "status": "validated", "proposed_by": "AI_ADVISOR"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"][0]["id"] == "tp1"
    assert body["data"][0]["status"] == "VALIDATED"


def test_replay_tuning_validations_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    class DummyTracker:
        def __init__(self, db):
            self.db = db

        def get_tuning_proposal_validations(self, tuning_proposal_id=None, passed=None, validator=None, limit=500):
            return [
                {
                    "id": "tv1",
                    "tuning_proposal_id": tuning_proposal_id,
                    "passed": passed,
                    "validator": validator or "DETERMINISTIC_GUARD",
                }
            ]

    monkeypatch.setattr("src.api.server.TelemetryTracker", DummyTracker)
    proposal_uuid = "33333333-3333-3333-3333-333333333333"
    response = client.get(
        "/api/replay/tuning-validations",
        params={"tuning_proposal_id": proposal_uuid, "passed": "true", "validator": "DETERMINISTIC_GUARD"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"][0]["id"] == "tv1"
    assert body["data"][0]["passed"] is True


def test_phase3_walk_forward_run_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    class DummyEngine:
        def __init__(self, db):
            self.db = db

        def run_validation(self, **kwargs):
            return {
                "ok": True,
                "walk_forward_run_id": "wf-1",
                "phase3_run_key": kwargs.get("phase3_run_key") or "wf-auto",
                "summary": {"fold_count": 4, "win_rate": 58.2},
            }

    monkeypatch.setattr("src.api.server.WalkForwardEngine", DummyEngine)

    response = client.post("/api/phase3/walk-forward/run", params={"run_id": "run-1", "fold_count": 4})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["walk_forward_run_id"] == "wf-1"
    assert body["data"]["summary"]["fold_count"] == 4


def test_phase3_tuning_propose_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    class DummyAdvisor:
        def __init__(self, db):
            self.db = db

        def create_proposal_for_walk_forward_run(self, walk_forward_run_id, proposed_by):
            return {
                "ok": True,
                "tuning_proposal_id": "tp-1",
                "status": "VALIDATED",
                "proposal_payload": {"sample_size": 80},
                "validations": [{"rule_code": "VALIDATION_OK"}],
            }

    monkeypatch.setattr("src.api.server.TuningAdvisor", DummyAdvisor)
    run_uuid = "55555555-5555-5555-5555-555555555555"
    response = client.post("/api/phase3/tuning/propose", params={"walk_forward_run_id": run_uuid, "actor": "AI_ADVISOR"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["tuning_proposal_id"] == "tp-1"
    assert body["data"]["status"] == "VALIDATED"


def test_phase3_tuning_transition_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    class DummyAdvisor:
        def __init__(self, db):
            self.db = db

        def transition_proposal_status(self, tuning_proposal_id, target_status, actor):
            return {"ok": True, "status": target_status, "note": f"{actor}:{tuning_proposal_id}"}

    monkeypatch.setattr("src.api.server.TuningAdvisor", DummyAdvisor)
    proposal_uuid = "66666666-6666-6666-6666-666666666666"
    response = client.post(
        "/api/phase3/tuning/transition",
        params={"tuning_proposal_id": proposal_uuid, "target_status": "APPROVED_MANUAL", "actor": "ops"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "APPROVED_MANUAL"


def test_phase3_tuning_apply_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.server.get_db", lambda: object())

    class DummyAdvisor:
        def __init__(self, db):
            self.db = db

        def apply_proposal(self, tuning_proposal_id, actor, dry_run=False):
            return {
                "ok": True,
                "status": "APPROVED_MANUAL" if dry_run else "APPLIED",
                "applied_keys": ["MIN_TOTAL_SCORE_TO_CANDIDATE"],
                "dry_run": dry_run,
            }

    monkeypatch.setattr("src.api.server.TuningAdvisor", DummyAdvisor)
    proposal_uuid = "77777777-7777-7777-7777-777777777777"
    response = client.post(
        "/api/phase3/tuning/apply",
        params={"tuning_proposal_id": proposal_uuid, "dry_run": "false"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "APPLIED"
    assert "MIN_TOTAL_SCORE_TO_CANDIDATE" in body["data"]["applied_keys"]
