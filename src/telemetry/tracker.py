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


def _num_or_none(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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

    def _insert_many(self, table: str, payload_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not self.db:
            return {"ok": False, "error": "db_not_configured"}
        if not payload_rows:
            return {"ok": True, "rows": []}
        try:
            result = self.db.table(table).insert(payload_rows).execute()
            return {"ok": True, "rows": result.data or []}
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

    def track_universe_snapshot_rows(self, snapshot_id: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        payload_rows: List[Dict[str, Any]] = []
        for row in rows:
            symbol = str(row.get("symbol", "")).upper().strip()
            if not symbol:
                continue
            payload_rows.append(
                {
                    "snapshot_id": str(snapshot_id),
                    "symbol": symbol,
                    "asset_class": str(row.get("asset_class", "crypto")).lower(),
                    "rank": int(row.get("rank", 0) or 0),
                    "source": row.get("source"),
                    "volume": _num_or_none(row.get("volume")),
                    "status": row.get("status"),
                    "whitelist_pass": bool(row.get("whitelist_pass", False)),
                    "inclusion_reason": row.get("inclusion_reason"),
                    "metadata": row.get("metadata") or {},
                    "updated_at": _utc_now_iso(),
                }
            )
        return self._insert_many("universe_snapshot", payload_rows)

    def track_feature_snapshot(
        self,
        run_id: str,
        symbol: str,
        timeframe: str,
        features: Dict[str, Any],
        ai_confidence: Optional[float] = None,
        sentiment_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        payload = {
            "run_id": str(run_id),
            "symbol": str(symbol).upper().strip(),
            "timeframe": str(timeframe),
            "close": _num_or_none(features.get("close")),
            "volume": _num_or_none(features.get("volume")),
            "quote_volume": _num_or_none(features.get("quote_volume")),
            "rsi": _num_or_none(features.get("rsi")),
            "macd": _num_or_none(features.get("macd")),
            "macd_signal": _num_or_none(features.get("macd_signal")),
            "ema_20": _num_or_none(features.get("ema_20")),
            "ema_50": _num_or_none(features.get("ema_50")),
            "ema_200": _num_or_none(features.get("ema_200")),
            "atr": _num_or_none(features.get("atr")),
            "adx": _num_or_none(features.get("adx")),
            "price_position_score": _num_or_none(features.get("price_position_score")),
            "ai_confidence": _num_or_none(ai_confidence),
            "sentiment_score": _num_or_none(sentiment_score),
            "features_json": features,
            "updated_at": _utc_now_iso(),
        }
        return self._insert("feature_snapshot", payload)

    def track_signal_score(
        self,
        run_id: str,
        symbol: str,
        timeframe: str,
        total_score: float,
        threshold: float,
        passed_threshold: bool,
        component_scores: Dict[str, Any],
        weighted_scores: Dict[str, Any],
        weights: Dict[str, Any],
        notes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "run_id": str(run_id),
            "symbol": str(symbol).upper().strip(),
            "timeframe": str(timeframe),
            "total_score": float(total_score),
            "threshold": float(threshold),
            "passed_threshold": bool(passed_threshold),
            "component_scores": component_scores or {},
            "weighted_scores": weighted_scores or {},
            "weights": weights or {},
            "notes": notes or [],
            "updated_at": _utc_now_iso(),
        }
        return self._insert("signal_score", payload)

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

    def get_feature_snapshots(
        self,
        symbol: Optional[str] = None,
        run_id: Optional[str] = None,
        timeframe: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        return self._query_with_filters(
            table="feature_snapshot",
            select=(
                "id,run_id,symbol,timeframe,close,volume,quote_volume,rsi,macd,macd_signal,"
                "ema_20,ema_50,ema_200,atr,adx,price_position_score,ai_confidence,sentiment_score,features_json,created_at"
            ),
            filters={"symbol": symbol, "run_id": run_id, "timeframe": timeframe},
            limit=limit,
        )

    def get_signal_scores(
        self,
        symbol: Optional[str] = None,
        run_id: Optional[str] = None,
        timeframe: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        return self._query_with_filters(
            table="signal_score",
            select=(
                "id,run_id,symbol,timeframe,total_score,threshold,passed_threshold,"
                "component_scores,weighted_scores,weights,notes,created_at"
            ),
            filters={"symbol": symbol, "run_id": run_id, "timeframe": timeframe},
            limit=limit,
        )

    def get_universe_snapshot(
        self,
        snapshot_id: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        return self._query_with_filters(
            table="universe_snapshot",
            select=(
                "id,snapshot_id,symbol,asset_class,rank,source,volume,status,whitelist_pass,inclusion_reason,metadata,created_at"
            ),
            filters={"snapshot_id": snapshot_id, "symbol": symbol},
            limit=limit,
        )

    def get_order_plans(
        self,
        symbol: Optional[str] = None,
        run_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        return self._query_with_filters(
            table="order_plans",
            select=(
                "id,run_id,signal_id,position_id,asset_id,symbol,side,timeframe,entry_price,stop_loss,"
                "take_profit_1,take_profit_2,risk_per_unit,tp1_partial_pct,breakeven_price,trailing_mode,"
                "trailing_value,status,plan_payload,notes,created_at"
            ),
            filters={"symbol": symbol, "run_id": run_id, "status": status},
            limit=limit,
        )

    def get_replay_bundle(self, run_id: str, limit: int = 200) -> Dict[str, Any]:
        return {
            "run_id": run_id,
            "ai_decisions": self.get_ai_decisions(run_id=run_id, limit=limit),
            "rule_evaluations": self.get_rule_evaluations(run_id=run_id, limit=limit),
            "post_trade_attribution": self.get_post_trade_attribution(run_id=run_id, limit=limit),
            "feature_snapshots": self.get_feature_snapshots(run_id=run_id, limit=limit),
            "signal_scores": self.get_signal_scores(run_id=run_id, limit=limit),
            "order_plans": self.get_order_plans(run_id=run_id, limit=limit),
        }
