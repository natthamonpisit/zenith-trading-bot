"""
P4 telemetry tracker and replay query utilities.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.database import get_db


def _stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TelemetryTracker:
    """
    Persist decision telemetry and provide replay-focused read queries.
    """

    def __init__(self, db: Any = None):
        self.db = db or get_db()

    def _insert(self, table: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.db:
            return {"ok": False, "error": "db_not_configured"}
        try:
            result = self.db.table(table).insert(payload).execute()
            row = result.data[0] if result.data else None
            return {"ok": True, "row": row}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _query_with_filters(
        self,
        table: str,
        select: str,
        filters: Optional[Dict[str, Any]] = None,
        order_by: str = "created_at",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        if not self.db:
            return []
        try:
            query = self.db.table(table).select(select).order(order_by, desc=True).limit(limit)
            for key, value in (filters or {}).items():
                if value is None or value == "":
                    continue
                query = query.eq(key, value)
            result = query.execute()
            return result.data or []
        except Exception:
            return []

    def track_ai_decision(
        self,
        run_id: str,
        symbol: str,
        timeframe: str,
        tier: str,
        model: str,
        prompt: Any,
        input_payload: Any,
        output_json: Dict[str, Any],
        confidence: float,
        latency_ms: int,
    ) -> Dict[str, Any]:
        payload = {
            "run_id": run_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "tier": tier,
            "model": model,
            "prompt_hash": _stable_hash(prompt),
            "input_hash": _stable_hash(input_payload),
            "output_json": output_json,
            "confidence": confidence,
            "latency_ms": latency_ms,
            "updated_at": _utc_now_iso(),
        }
        return self._insert("ai_decisions", payload)

    def track_rule_evaluation(
        self,
        run_id: str,
        symbol: str,
        rule_name: str,
        passed: bool,
        observed_value: Any,
        threshold_value: Any,
        reason: str,
    ) -> Dict[str, Any]:
        payload = {
            "run_id": run_id,
            "symbol": symbol,
            "rule_name": rule_name,
            "passed": passed,
            "observed_value": str(observed_value) if observed_value is not None else None,
            "threshold_value": str(threshold_value) if threshold_value is not None else None,
            "reason": reason,
            "updated_at": _utc_now_iso(),
        }
        return self._insert("rule_evaluations", payload)

    def track_post_trade_attribution(
        self,
        position_id: Optional[str],
        run_id: Optional[str],
        outcome: str,
        pnl: float,
        mfe: Optional[float] = None,
        mae: Optional[float] = None,
        exit_reason: Optional[str] = None,
        violated_rule: Optional[str] = None,
        ai_vs_rule_alignment: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "position_id": position_id,
            "run_id": run_id,
            "outcome": outcome,
            "pnl": pnl,
            "mfe": mfe,
            "mae": mae,
            "exit_reason": exit_reason,
            "violated_rule": violated_rule,
            "ai_vs_rule_alignment": ai_vs_rule_alignment,
            "notes": notes,
            "updated_at": _utc_now_iso(),
        }
        return self._insert("post_trade_attribution", payload)

    def get_ai_decisions(
        self,
        symbol: Optional[str] = None,
        run_id: Optional[str] = None,
        tier: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return self._query_with_filters(
            table="ai_decisions",
            select="id,run_id,symbol,timeframe,tier,model,confidence,latency_ms,output_json,created_at",
            filters={"symbol": symbol, "run_id": run_id, "tier": tier},
            limit=limit,
        )

    def get_rule_evaluations(
        self,
        symbol: Optional[str] = None,
        run_id: Optional[str] = None,
        rule_name: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        return self._query_with_filters(
            table="rule_evaluations",
            select="id,run_id,symbol,rule_name,passed,observed_value,threshold_value,reason,created_at",
            filters={"symbol": symbol, "run_id": run_id, "rule_name": rule_name},
            limit=limit,
        )

    def get_post_trade_attribution(
        self,
        run_id: Optional[str] = None,
        outcome: Optional[str] = None,
        position_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        return self._query_with_filters(
            table="post_trade_attribution",
            select="id,position_id,run_id,outcome,pnl,mfe,mae,exit_reason,violated_rule,ai_vs_rule_alignment,notes,created_at",
            filters={"run_id": run_id, "outcome": outcome, "position_id": position_id},
            limit=limit,
        )

    def get_replay_bundle(self, run_id: str, limit: int = 200) -> Dict[str, Any]:
        return {
            "run_id": run_id,
            "ai_decisions": self.get_ai_decisions(run_id=run_id, limit=limit),
            "rule_evaluations": self.get_rule_evaluations(run_id=run_id, limit=limit),
            "post_trade_attribution": self.get_post_trade_attribution(run_id=run_id, limit=limit),
        }
