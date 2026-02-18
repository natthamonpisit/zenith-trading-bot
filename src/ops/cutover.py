"""
P7 cutover controls for dashboard primary/fallback switching.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _clean_cfg_value(raw: Any, default: str = "") -> str:
    if raw is None:
        return default
    return str(raw).replace('"', "").strip()


def _to_bool(raw: Any, default: bool = False) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        val = raw.strip().lower()
        if val in {"true", "1", "yes"}:
            return True
        if val in {"false", "0", "no"}:
            return False
    return default


class CutoverService:
    ALLOWED_PRIMARY = {"REACT", "STREAMLIT"}

    def __init__(self, db: Any):
        self.db = db

    def _get_config(self, key: str) -> Optional[Any]:
        try:
            result = self.db.table("bot_config").select("value").eq("key", key).limit(1).execute()
            if result.data:
                return result.data[0].get("value")
        except Exception:
            return None
        return None

    def _upsert_config(self, key: str, value: Any, description: Optional[str] = None) -> None:
        payload = {"key": key, "value": value}
        if description:
            payload["description"] = description
        self.db.table("bot_config").upsert(payload).execute()

    def get_status(self) -> Dict[str, Any]:
        primary = _clean_cfg_value(self._get_config("PRIMARY_DASHBOARD"), default="STREAMLIT").upper()
        if primary not in self.ALLOWED_PRIMARY:
            primary = "STREAMLIT"

        fallback_enabled = _to_bool(self._get_config("STREAMLIT_FALLBACK_ENABLED"), default=True)
        dual_run_mode = _clean_cfg_value(self._get_config("DUAL_RUN_MODE"), default="ENABLED").upper()
        cutover_completed_at = self._get_config("CUTOVER_COMPLETED_AT")

        return {
            "primary_dashboard": primary,
            "streamlit_fallback_enabled": fallback_enabled,
            "dual_run_mode": dual_run_mode,
            "cutover_completed_at": cutover_completed_at,
            "cutover_ready": primary == "REACT" and (dual_run_mode in {"DISABLED", "ENABLED"}),
        }

    def apply_cutover(self, primary_dashboard: str, fallback_enabled: bool, actor: str = "api") -> Dict[str, Any]:
        normalized = primary_dashboard.upper().strip()
        if normalized not in self.ALLOWED_PRIMARY:
            raise ValueError("primary_dashboard must be REACT or STREAMLIT")

        previous_status = self.get_status()
        old_value = previous_status.get("primary_dashboard")

        now_iso = datetime.now(timezone.utc).isoformat()
        self._upsert_config("PRIMARY_DASHBOARD", f'"{normalized}"', "Primary dashboard interface")
        self._upsert_config("STREAMLIT_FALLBACK_ENABLED", "true" if fallback_enabled else "false", "Enable Streamlit fallback")
        if normalized == "REACT":
            self._upsert_config("CUTOVER_COMPLETED_AT", f'"{now_iso}"', "React cutover completed timestamp")

        try:
            self.db.table("audit_log").insert(
                {
                    "event_type": "CONFIG_CHANGED",
                    "key": "PRIMARY_DASHBOARD",
                    "old_value": str(old_value),
                    "new_value": normalized,
                    "user": actor,
                    "reason": "P7 cutover operation",
                }
            ).execute()
        except Exception:
            pass

        return self.get_status()
