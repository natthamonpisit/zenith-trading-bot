"""
P4 telemetry tracker and replay query utilities.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.database import get_db
from src.ops.phase3_metrics import increment_counter


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

    def _update_by_id(self, table: str, row_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.db:
            return {"ok": False, "error": "db_not_configured"}
        if not row_id:
            return {"ok": False, "error": "id_required"}
        if not payload:
            return {"ok": True, "row": None}
        try:
            result = self.db.table(table).update(payload).eq("id", row_id).execute()
            row = result.data[0] if result.data else None
            return {"ok": True, "row": row}
        except Exception as exc:
            if table in {"walk_forward_runs", "walk_forward_fold_results", "tuning_proposals", "tuning_proposal_validations"}:
                increment_counter("phase3_query_error_count", 1)
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
            if table in {"walk_forward_runs", "walk_forward_fold_results", "tuning_proposals", "tuning_proposal_validations"}:
                increment_counter("phase3_query_error_count", 1)
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

    def track_walk_forward_run(
        self,
        phase3_run_key: str,
        status: str,
        run_id: Optional[str] = None,
        timeframe: Optional[str] = None,
        dataset_scope: Optional[str] = None,
        sample_size: int = 0,
        fold_count: int = 0,
        metrics_json: Optional[Dict[str, Any]] = None,
        params_json: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_status = str(status or "PENDING").upper()
        payload = {
            "run_id": run_id,
            "phase3_run_key": str(phase3_run_key),
            "timeframe": timeframe,
            "dataset_scope": dataset_scope,
            "sample_size": int(sample_size or 0),
            "fold_count": int(fold_count or 0),
            "status": normalized_status,
            "metrics_json": metrics_json or {},
            "params_json": params_json or {},
            "error_message": error_message,
            "started_at": started_at,
            "completed_at": completed_at,
            "updated_at": _utc_now_iso(),
        }
        return self._insert("walk_forward_runs", payload)

    def track_walk_forward_fold_results(
        self,
        walk_forward_run_id: str,
        fold_rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload_rows: List[Dict[str, Any]] = []
        for row in fold_rows:
            payload_rows.append(
                {
                    "walk_forward_run_id": str(walk_forward_run_id),
                    "fold_index": int(row.get("fold_index", 0) or 0),
                    "train_from": row.get("train_from"),
                    "train_to": row.get("train_to"),
                    "test_from": row.get("test_from"),
                    "test_to": row.get("test_to"),
                    "sample_size": int(row.get("sample_size", 0) or 0),
                    "metrics_json": row.get("metrics_json") or {},
                    "notes": row.get("notes"),
                    "updated_at": _utc_now_iso(),
                }
            )
        return self._insert_many("walk_forward_fold_results", payload_rows)

    def track_tuning_proposal(
        self,
        status: str,
        proposal_payload: Dict[str, Any],
        walk_forward_run_id: Optional[str] = None,
        proposed_by: str = "AI_ADVISOR",
        config_snapshot: Optional[Dict[str, Any]] = None,
        config_hash: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "walk_forward_run_id": walk_forward_run_id,
            "status": str(status or "DRAFT").upper(),
            "proposed_by": str(proposed_by or "AI_ADVISOR"),
            "proposal_payload": proposal_payload or {},
            "config_snapshot": config_snapshot or {},
            "config_hash": config_hash,
            "notes": notes,
            "updated_at": _utc_now_iso(),
        }
        return self._insert("tuning_proposals", payload)

    def track_tuning_proposal_validation(
        self,
        tuning_proposal_id: str,
        passed: bool,
        rule_code: str,
        message: str,
        severity: str = "ERROR",
        validator: str = "DETERMINISTIC_GUARD",
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_severity = str(severity or "ERROR").upper()
        payload = {
            "tuning_proposal_id": str(tuning_proposal_id),
            "validator": str(validator or "DETERMINISTIC_GUARD"),
            "passed": bool(passed),
            "severity": normalized_severity,
            "rule_code": str(rule_code or ""),
            "message": str(message or ""),
            "details": details or {},
            "updated_at": _utc_now_iso(),
        }
        return self._insert("tuning_proposal_validations", payload)

    def update_walk_forward_run(
        self,
        walk_forward_run_id: str,
        status: Optional[str] = None,
        sample_size: Optional[int] = None,
        fold_count: Optional[int] = None,
        metrics_json: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"updated_at": _utc_now_iso()}
        if status is not None:
            payload["status"] = str(status).upper()
        if sample_size is not None:
            payload["sample_size"] = int(sample_size)
        if fold_count is not None:
            payload["fold_count"] = int(fold_count)
        if metrics_json is not None:
            payload["metrics_json"] = metrics_json
        if error_message is not None:
            payload["error_message"] = error_message
        if completed_at is not None:
            payload["completed_at"] = completed_at
        return self._update_by_id("walk_forward_runs", walk_forward_run_id, payload)

    def update_tuning_proposal(
        self,
        tuning_proposal_id: str,
        status: Optional[str] = None,
        notes: Optional[str] = None,
        proposal_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"updated_at": _utc_now_iso()}
        if status is not None:
            payload["status"] = str(status).upper()
        if notes is not None:
            payload["notes"] = notes
        if proposal_payload is not None:
            payload["proposal_payload"] = proposal_payload
        return self._update_by_id("tuning_proposals", tuning_proposal_id, payload)

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

    def get_walk_forward_runs(
        self,
        run_id: Optional[str] = None,
        phase3_run_key: Optional[str] = None,
        status: Optional[str] = None,
        timeframe: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        return self._query_with_filters(
            table="walk_forward_runs",
            select=(
                "id,run_id,phase3_run_key,timeframe,dataset_scope,sample_size,fold_count,status,metrics_json,params_json,"
                "error_message,started_at,completed_at,created_at"
            ),
            filters={
                "run_id": run_id,
                "phase3_run_key": phase3_run_key,
                "status": status,
                "timeframe": timeframe,
            },
            limit=limit,
        )

    def get_walk_forward_fold_results(
        self,
        walk_forward_run_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        rows = self._query_with_filters(
            table="walk_forward_fold_results",
            select=(
                "id,walk_forward_run_id,fold_index,train_from,train_to,test_from,test_to,sample_size,metrics_json,notes,created_at"
            ),
            filters={"walk_forward_run_id": walk_forward_run_id},
            order_by="fold_index",
            limit=limit,
        )
        return sorted(rows, key=lambda item: int(item.get("fold_index") or 0))

    def get_tuning_proposals(
        self,
        walk_forward_run_id: Optional[str] = None,
        status: Optional[str] = None,
        proposed_by: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        return self._query_with_filters(
            table="tuning_proposals",
            select=(
                "id,walk_forward_run_id,status,proposed_by,proposal_payload,config_snapshot,config_hash,notes,created_at"
            ),
            filters={
                "walk_forward_run_id": walk_forward_run_id,
                "status": status,
                "proposed_by": proposed_by,
            },
            limit=limit,
        )

    def get_tuning_proposal_by_id(self, tuning_proposal_id: str) -> Optional[Dict[str, Any]]:
        rows = self._query_with_filters(
            table="tuning_proposals",
            select="id,walk_forward_run_id,status,proposed_by,proposal_payload,config_snapshot,config_hash,notes,created_at",
            filters={"id": tuning_proposal_id},
            limit=1,
        )
        return rows[0] if rows else None

    def get_walk_forward_run_by_id(self, walk_forward_run_id: str) -> Optional[Dict[str, Any]]:
        rows = self._query_with_filters(
            table="walk_forward_runs",
            select=(
                "id,run_id,phase3_run_key,timeframe,dataset_scope,sample_size,fold_count,status,metrics_json,params_json,"
                "error_message,started_at,completed_at,created_at"
            ),
            filters={"id": walk_forward_run_id},
            limit=1,
        )
        return rows[0] if rows else None

    def get_tuning_proposal_validations(
        self,
        tuning_proposal_id: Optional[str] = None,
        passed: Optional[bool] = None,
        validator: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        return self._query_with_filters(
            table="tuning_proposal_validations",
            select=(
                "id,tuning_proposal_id,validator,passed,severity,rule_code,message,details,created_at"
            ),
            filters={
                "tuning_proposal_id": tuning_proposal_id,
                "passed": passed,
                "validator": validator,
            },
            limit=limit,
        )

    def get_replay_bundle(self, run_id: str, limit: int = 200) -> Dict[str, Any]:
        walk_forward_runs = self.get_walk_forward_runs(run_id=run_id, limit=min(limit, 200))
        walk_forward_run_ids = [row.get("id") for row in walk_forward_runs if row.get("id")]

        walk_forward_folds: List[Dict[str, Any]] = []
        tuning_proposals: List[Dict[str, Any]] = []
        tuning_validations: List[Dict[str, Any]] = []

        for walk_forward_run_id in walk_forward_run_ids[:10]:
            walk_forward_folds.extend(
                self.get_walk_forward_fold_results(walk_forward_run_id=walk_forward_run_id, limit=min(limit, 100))
            )
            tuning_proposals.extend(
                self.get_tuning_proposals(walk_forward_run_id=walk_forward_run_id, limit=min(limit, 100))
            )

        for proposal in tuning_proposals[:20]:
            proposal_id = proposal.get("id")
            if not proposal_id:
                continue
            tuning_validations.extend(
                self.get_tuning_proposal_validations(tuning_proposal_id=proposal_id, limit=min(limit, 100))
            )

        return {
            "run_id": run_id,
            "ai_decisions": self.get_ai_decisions(run_id=run_id, limit=limit),
            "rule_evaluations": self.get_rule_evaluations(run_id=run_id, limit=limit),
            "post_trade_attribution": self.get_post_trade_attribution(run_id=run_id, limit=limit),
            "feature_snapshots": self.get_feature_snapshots(run_id=run_id, limit=limit),
            "signal_scores": self.get_signal_scores(run_id=run_id, limit=limit),
            "order_plans": self.get_order_plans(run_id=run_id, limit=limit),
            "walk_forward_runs": walk_forward_runs,
            "walk_forward_fold_results": walk_forward_folds,
            "tuning_proposals": tuning_proposals,
            "tuning_proposal_validations": tuning_validations,
        }
