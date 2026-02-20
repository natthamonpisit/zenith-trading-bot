from __future__ import annotations

import threading
from typing import Any, Dict


_lock = threading.Lock()
_COUNTERS: Dict[str, int] = {
    "phase3_validation_reject_count": 0,
    "phase3_query_error_count": 0,
}
_DURATIONS: Dict[str, Dict[str, float]] = {
    "phase3_run_duration_ms": {"count": 0.0, "total": 0.0, "last": 0.0},
}


def increment_counter(name: str, amount: int = 1) -> None:
    if amount <= 0:
        return
    with _lock:
        _COUNTERS[name] = int(_COUNTERS.get(name, 0)) + int(amount)


def observe_duration_ms(name: str, duration_ms: float) -> None:
    safe_duration = max(0.0, float(duration_ms or 0.0))
    with _lock:
        bucket = _DURATIONS.setdefault(name, {"count": 0.0, "total": 0.0, "last": 0.0})
        bucket["count"] += 1.0
        bucket["total"] += safe_duration
        bucket["last"] = safe_duration


def snapshot_metrics() -> Dict[str, Any]:
    with _lock:
        duration_stats = {}
        for name, values in _DURATIONS.items():
            count = float(values.get("count", 0.0))
            total = float(values.get("total", 0.0))
            last = float(values.get("last", 0.0))
            avg = (total / count) if count > 0 else 0.0
            duration_stats[name] = {
                "count": int(count),
                "total": round(total, 3),
                "avg": round(avg, 3),
                "last": round(last, 3),
            }

        return {
            "counters": dict(_COUNTERS),
            "durations_ms": duration_stats,
        }

