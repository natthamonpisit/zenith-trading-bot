from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.database import get_db
from src.ops.phase3_metrics import observe_duration_ms
from src.telemetry.tracker import TelemetryTracker


def _to_float(raw: Any, default: float = 0.0) -> float:
    try:
        if raw is None:
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FoldSplit:
    fold_index: int
    train_rows: List[Dict[str, Any]]
    test_rows: List[Dict[str, Any]]
    train_from: Optional[datetime]
    train_to: Optional[datetime]
    test_from: Optional[datetime]
    test_to: Optional[datetime]


def calculate_fold_metrics(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    pnls = [_to_float(row.get("pnl"), default=0.0) for row in rows]
    sample_size = len(pnls)
    if sample_size == 0:
        return {
            "sample_size": 0.0,
            "win_rate": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "net_pnl": 0.0,
        }

    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    win_rate = (len(wins) / sample_size) * 100.0
    expectancy = sum(pnls) / sample_size

    positive_pnl = sum(wins)
    negative_pnl = abs(sum(losses))
    if negative_pnl <= 0:
        profit_factor = 9999.0 if positive_pnl > 0 else 0.0
    else:
        profit_factor = positive_pnl / negative_pnl

    equity = 0.0
    peak = 0.0
    max_drawdown_pct = 0.0
    for pnl in pnls:
        equity += pnl
        if equity > peak:
            peak = equity
        if peak > 0:
            drawdown_pct = ((peak - equity) / peak) * 100.0
            if drawdown_pct > max_drawdown_pct:
                max_drawdown_pct = drawdown_pct

    return {
        "sample_size": float(sample_size),
        "win_rate": round(win_rate, 4),
        "expectancy": round(expectancy, 6),
        "profit_factor": round(profit_factor, 6),
        "max_drawdown_pct": round(max_drawdown_pct, 6),
        "net_pnl": round(sum(pnls), 6),
    }


def build_walk_forward_folds(
    rows: List[Dict[str, Any]],
    fold_count: int = 5,
    min_train_size: int = 30,
    min_test_size: int = 10,
) -> List[FoldSplit]:
    if not rows:
        return []

    normalized_rows = []
    for row in rows:
        ts = _parse_ts(row.get("created_at"))
        if ts is None:
            continue
        normalized = dict(row)
        normalized["_ts"] = ts
        normalized_rows.append(normalized)

    normalized_rows.sort(key=lambda item: item["_ts"])
    total = len(normalized_rows)
    if total < (min_train_size + min_test_size):
        return []

    requested_folds = max(1, int(fold_count or 1))
    max_folds = max(1, (total - min_train_size) // max(1, min_test_size))
    effective_folds = min(requested_folds, max_folds)

    base_test_size = max(min_test_size, (total - min_train_size) // effective_folds)
    splits: List[FoldSplit] = []

    for fold_idx in range(effective_folds):
        test_start = min_train_size + (fold_idx * base_test_size)
        if test_start >= total:
            break
        test_end = min(total, test_start + base_test_size)
        if (test_end - test_start) < min_test_size:
            break

        train_rows = normalized_rows[:test_start]
        test_rows = normalized_rows[test_start:test_end]
        if not train_rows or not test_rows:
            continue

        if train_rows[-1]["_ts"] >= test_rows[0]["_ts"]:
            raise ValueError(
                f"data_leakage_detected fold={fold_idx + 1} train_to={train_rows[-1]['_ts']} test_from={test_rows[0]['_ts']}"
            )

        splits.append(
            FoldSplit(
                fold_index=fold_idx + 1,
                train_rows=train_rows,
                test_rows=test_rows,
                train_from=train_rows[0]["_ts"],
                train_to=train_rows[-1]["_ts"],
                test_from=test_rows[0]["_ts"],
                test_to=test_rows[-1]["_ts"],
            )
        )

    return splits


class WalkForwardEngine:
    def __init__(self, db: Any = None, tracker: Optional[TelemetryTracker] = None):
        self.db = db or get_db()
        self.tracker = tracker or TelemetryTracker(db=self.db)

    def _fetch_post_trade_rows(self, run_id: Optional[str] = None, limit: int = 3000) -> List[Dict[str, Any]]:
        if not self.db:
            return []
        try:
            query = (
                self.db.table("post_trade_attribution")
                .select("id,run_id,outcome,pnl,mfe,mae,exit_reason,created_at")
                .order("created_at", desc=False)
                .limit(max(50, min(int(limit or 3000), 5000)))
            )
            if run_id:
                query = query.eq("run_id", run_id)
            result = query.execute()
            return result.data or []
        except Exception:
            return []

    def run_validation(
        self,
        run_id: Optional[str] = None,
        timeframe: str = "1h",
        dataset_scope: str = "GLOBAL",
        fold_count: int = 5,
        min_sample_size: int = 50,
        min_train_size: int = 30,
        min_test_size: int = 10,
        row_limit: int = 3000,
        phase3_run_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        started_at = _utc_now_iso()
        perf_start = time.perf_counter()
        normalized_key = phase3_run_key or f"wf-{int(time.time())}"
        run_row_id: Optional[str] = None

        try:
            seed = self.tracker.track_walk_forward_run(
                run_id=run_id,
                phase3_run_key=normalized_key,
                timeframe=timeframe,
                dataset_scope=dataset_scope,
                sample_size=0,
                fold_count=0,
                status="RUNNING",
                params_json={
                    "fold_count": int(fold_count),
                    "min_sample_size": int(min_sample_size),
                    "min_train_size": int(min_train_size),
                    "min_test_size": int(min_test_size),
                    "row_limit": int(row_limit),
                },
                started_at=started_at,
            )
            run_row_id = seed.get("row", {}).get("id") if seed.get("ok") else None

            rows = self._fetch_post_trade_rows(run_id=run_id, limit=row_limit)
            sample_size = len(rows)

            folds = build_walk_forward_folds(
                rows=rows,
                fold_count=fold_count,
                min_train_size=min_train_size,
                min_test_size=min_test_size,
            )
            if not folds:
                metrics = {
                    "sample_size": sample_size,
                    "fold_count": 0,
                    "low_confidence": True,
                    "reason": "insufficient_data_for_fold_split",
                }
                if run_row_id:
                    self.tracker.update_walk_forward_run(
                        walk_forward_run_id=run_row_id,
                        status="COMPLETED",
                        sample_size=sample_size,
                        fold_count=0,
                        metrics_json=metrics,
                        completed_at=_utc_now_iso(),
                    )
                duration_ms = (time.perf_counter() - perf_start) * 1000.0
                observe_duration_ms("phase3_run_duration_ms", duration_ms)
                return {
                    "ok": True,
                    "walk_forward_run_id": run_row_id,
                    "phase3_run_key": normalized_key,
                    "summary": metrics,
                }

            fold_rows: List[Dict[str, Any]] = []
            fold_metrics: List[Dict[str, float]] = []
            for split in folds:
                metrics = calculate_fold_metrics(split.test_rows)
                fold_metrics.append(metrics)
                fold_rows.append(
                    {
                        "fold_index": split.fold_index,
                        "train_from": split.train_from.isoformat() if split.train_from else None,
                        "train_to": split.train_to.isoformat() if split.train_to else None,
                        "test_from": split.test_from.isoformat() if split.test_from else None,
                        "test_to": split.test_to.isoformat() if split.test_to else None,
                        "sample_size": int(metrics.get("sample_size", 0)),
                        "metrics_json": metrics,
                        "notes": None,
                    }
                )

            if run_row_id and fold_rows:
                self.tracker.track_walk_forward_fold_results(
                    walk_forward_run_id=run_row_id,
                    fold_rows=fold_rows,
                )

            def _avg(metric_key: str) -> float:
                values = [
                    _to_float(item.get(metric_key), default=0.0)
                    for item in fold_metrics
                    if math.isfinite(_to_float(item.get(metric_key), default=0.0))
                ]
                if not values:
                    return 0.0
                return sum(values) / len(values)

            summary = {
                "sample_size": sample_size,
                "fold_count": len(fold_metrics),
                "win_rate": round(_avg("win_rate"), 4),
                "expectancy": round(_avg("expectancy"), 6),
                "profit_factor": round(_avg("profit_factor"), 6),
                "max_drawdown_pct": round(_avg("max_drawdown_pct"), 6),
                "net_pnl": round(_avg("net_pnl"), 6),
                "low_confidence": sample_size < max(min_sample_size, min_train_size + min_test_size),
            }

            if run_row_id:
                self.tracker.update_walk_forward_run(
                    walk_forward_run_id=run_row_id,
                    status="COMPLETED",
                    sample_size=sample_size,
                    fold_count=len(fold_metrics),
                    metrics_json=summary,
                    completed_at=_utc_now_iso(),
                )

            duration_ms = (time.perf_counter() - perf_start) * 1000.0
            observe_duration_ms("phase3_run_duration_ms", duration_ms)
            return {
                "ok": True,
                "walk_forward_run_id": run_row_id,
                "phase3_run_key": normalized_key,
                "summary": summary,
            }
        except Exception as exc:
            if run_row_id:
                self.tracker.update_walk_forward_run(
                    walk_forward_run_id=run_row_id,
                    status="FAILED",
                    error_message=str(exc)[:280],
                    completed_at=_utc_now_iso(),
                )
            duration_ms = (time.perf_counter() - perf_start) * 1000.0
            observe_duration_ms("phase3_run_duration_ms", duration_ms)
            return {
                "ok": False,
                "walk_forward_run_id": run_row_id,
                "phase3_run_key": normalized_key,
                "error": str(exc)[:280],
            }

