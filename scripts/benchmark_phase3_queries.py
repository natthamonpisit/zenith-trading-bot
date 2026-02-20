#!/usr/bin/env python3
"""
Quick benchmark for phase3 replay queries.
Run manually before enabling phase3 flags in production.
"""

from __future__ import annotations

import os
import sys
import time

# Ensure project root is importable when script is run directly.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.database import get_db
from src.telemetry.tracker import TelemetryTracker


def _measure(label, fn):
    started = time.perf_counter()
    rows = fn()
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    print(f"{label:32s} rows={len(rows):4d}  time={elapsed_ms:8.2f} ms")
    return elapsed_ms


def main():
    db = get_db()
    if not db:
        print("Database not configured.")
        return

    tracker = TelemetryTracker(db=db)
    print("Phase3 query benchmark")
    print("-" * 60)
    _measure("walk_forward_runs(limit=100)", lambda: tracker.get_walk_forward_runs(limit=100))
    _measure(
        "tuning_proposals(limit=100)",
        lambda: tracker.get_tuning_proposals(limit=100),
    )
    proposals = tracker.get_tuning_proposals(limit=20)
    proposal_id = proposals[0]["id"] if proposals else None
    _measure(
        "tuning_validations(limit=200)",
        lambda: tracker.get_tuning_proposal_validations(tuning_proposal_id=proposal_id, limit=200),
    )


if __name__ == "__main__":
    main()
