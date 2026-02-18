"""
P6 hardening service: dual-run parity and alerting.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_cfg_value(raw: Any, default: str = "") -> str:
    if raw is None:
        return default
    return str(raw).replace('"', "").strip()


def compare_dashboard_summary(
    primary: Dict[str, Any],
    secondary: Dict[str, Any],
    tolerance_pct: float = 2.0,
) -> Dict[str, Any]:
    fields = ["equity", "daily_pnl", "drawdown_pct", "open_positions", "win_rate"]
    differences = []

    for field in fields:
        left = _safe_float(primary.get(field))
        right = _safe_float(secondary.get(field))
        base = max(1.0, abs(left))
        diff_pct = abs(left - right) / base * 100
        if diff_pct > tolerance_pct:
            differences.append(
                {
                    "field": field,
                    "primary": left,
                    "secondary": right,
                    "diff_pct": round(diff_pct, 4),
                }
            )

    return {
        "parity_passed": len(differences) == 0,
        "tolerance_pct": tolerance_pct,
        "differences": differences,
    }


class HardeningService:
    def __init__(self, db: Any):
        self.db = db

    def _get_bot_config_value(self, key: str) -> Optional[Any]:
        try:
            result = self.db.table("bot_config").select("value").eq("key", key).limit(1).execute()
            if result.data:
                return result.data[0].get("value")
        except Exception:
            pass
        return None

    def get_dual_run_mode(self) -> str:
        val = _clean_cfg_value(self._get_bot_config_value("DUAL_RUN_MODE"), default="ENABLED")
        mode = val.upper()
        return mode if mode in {"ENABLED", "DISABLED"} else "ENABLED"

    def get_heartbeat_age_sec(self) -> Optional[int]:
        raw = self._get_bot_config_value("LAST_HEARTBEAT")
        if raw is None:
            return None
        ts = _safe_float(raw, default=0.0)
        if ts <= 0:
            return None
        return int(max(0.0, time.time() - ts))

    def get_recent_errors(self, limit: int = 100) -> List[Dict[str, Any]]:
        try:
            rows = (
                self.db.table("system_logs")
                .select("id,level,role,message,created_at")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
                .data
                or []
            )
            return rows
        except Exception:
            return []

    def evaluate_alerts(self) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        heartbeat_age = self.get_heartbeat_age_sec()
        if heartbeat_age is None:
            alerts.append(
                {
                    "severity": "WARNING",
                    "code": "HEARTBEAT_MISSING",
                    "message": "No heartbeat value in bot_config",
                }
            )
        elif heartbeat_age > 120:
            alerts.append(
                {
                    "severity": "CRITICAL",
                    "code": "HEARTBEAT_STALE",
                    "message": f"Heartbeat stale for {heartbeat_age}s",
                }
            )

        logs = self.get_recent_errors(limit=80)
        error_count = len([row for row in logs if str(row.get("level", "")).upper() == "ERROR"])
        warning_count = len([row for row in logs if str(row.get("level", "")).upper() == "WARNING"])
        if error_count >= 10:
            alerts.append(
                {
                    "severity": "CRITICAL",
                    "code": "ERROR_RATE_HIGH",
                    "message": f"High error rate: {error_count} errors in recent logs",
                }
            )
        elif warning_count >= 15:
            alerts.append(
                {
                    "severity": "WARNING",
                    "code": "WARNING_RATE_HIGH",
                    "message": f"High warning rate: {warning_count} warnings in recent logs",
                }
            )
        return alerts

    def get_health_snapshot(self) -> Dict[str, Any]:
        return {
            "dual_run_mode": self.get_dual_run_mode(),
            "heartbeat_age_sec": self.get_heartbeat_age_sec(),
            "alerts": self.evaluate_alerts(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
