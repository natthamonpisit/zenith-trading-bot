from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.database import get_db
from src.ops.phase3_metrics import increment_counter
from src.telemetry.tracker import TelemetryTracker


def _to_float(raw: Any, default: float = 0.0) -> float:
    try:
        if raw is None:
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def _clean(raw: Any, default: str = "") -> str:
    if raw is None:
        return default
    return str(raw).replace('"', "").strip()


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TuningAdvisor:
    _ALLOWED_TRANSITIONS = {
        "DRAFT": {"VALIDATED", "REJECTED", "EXPIRED"},
        "VALIDATED": {"APPROVED_MANUAL", "REJECTED", "EXPIRED"},
        "APPROVED_MANUAL": {"APPLIED", "EXPIRED"},
        "REJECTED": {"DRAFT", "EXPIRED"},
        "APPLIED": set(),
        "EXPIRED": set(),
    }
    _ALLOWED_KEYS = {
        "MIN_TOTAL_SCORE_TO_CANDIDATE",
        "ENABLE_SIGNAL_SCORE_GATE",
        "SCORE_LIQUIDITY_MIN_VOLUME",
        "SCORE_WEIGHT_TREND",
        "SCORE_WEIGHT_MOMENTUM",
        "SCORE_WEIGHT_VOLATILITY",
        "SCORE_WEIGHT_LIQUIDITY",
        "SCORE_WEIGHT_STRUCTURE",
        "SCORE_WEIGHT_PORTFOLIO",
    }

    def __init__(self, db: Any = None, tracker: Optional[TelemetryTracker] = None):
        self.db = db or get_db()
        self.tracker = tracker or TelemetryTracker(db=self.db)

    def _fetch_config_map(self) -> Dict[str, str]:
        if not self.db:
            return {}
        try:
            rows = self.db.table("bot_config").select("key,value").execute().data or []
            return {str(row.get("key", "")): _clean(row.get("value")) for row in rows}
        except Exception:
            return {}

    def _config_bounds(self) -> Dict[str, Tuple[float, float]]:
        return {
            "MIN_TOTAL_SCORE_TO_CANDIDATE": (0.0, 100.0),
            "SCORE_LIQUIDITY_MIN_VOLUME": (1.0, 1_000_000_000.0),
            "SCORE_WEIGHT_TREND": (0.0, 100.0),
            "SCORE_WEIGHT_MOMENTUM": (0.0, 100.0),
            "SCORE_WEIGHT_VOLATILITY": (0.0, 100.0),
            "SCORE_WEIGHT_LIQUIDITY": (0.0, 100.0),
            "SCORE_WEIGHT_STRUCTURE": (0.0, 100.0),
            "SCORE_WEIGHT_PORTFOLIO": (0.0, 100.0),
        }

    def _normalize_weights(self, updates: Dict[str, float]) -> Dict[str, float]:
        weight_keys = [key for key in updates.keys() if key.startswith("SCORE_WEIGHT_")]
        if not weight_keys:
            return updates

        total = sum(max(0.0, _to_float(updates.get(key), default=0.0)) for key in weight_keys)
        if total <= 0:
            return updates
        scale = 100.0 / total
        normalized = dict(updates)
        for key in weight_keys:
            normalized[key] = round(_clamp(_to_float(normalized.get(key), default=0.0) * scale, 0.0, 100.0), 4)
        return normalized

    def build_proposal_payload(
        self,
        metrics_summary: Dict[str, Any],
        sample_size: int,
        current_config: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        cfg = current_config or self._fetch_config_map()
        win_rate = _to_float(metrics_summary.get("win_rate"), default=0.0)
        expectancy = _to_float(metrics_summary.get("expectancy"), default=0.0)
        max_dd = _to_float(metrics_summary.get("max_drawdown_pct"), default=0.0)

        threshold = _to_float(cfg.get("MIN_TOTAL_SCORE_TO_CANDIDATE"), default=60.0)
        trend_w = _to_float(cfg.get("SCORE_WEIGHT_TREND"), default=25.0)
        momentum_w = _to_float(cfg.get("SCORE_WEIGHT_MOMENTUM"), default=20.0)
        volatility_w = _to_float(cfg.get("SCORE_WEIGHT_VOLATILITY"), default=15.0)
        liquidity_w = _to_float(cfg.get("SCORE_WEIGHT_LIQUIDITY"), default=20.0)
        structure_w = _to_float(cfg.get("SCORE_WEIGHT_STRUCTURE"), default=10.0)
        portfolio_w = _to_float(cfg.get("SCORE_WEIGHT_PORTFOLIO"), default=10.0)

        rationale: List[str] = []
        if win_rate < 45.0 or expectancy < 0:
            threshold += 2.0
            trend_w += 1.0
            liquidity_w += 2.0
            momentum_w -= 1.0
            rationale.append("defensive_bias_due_to_low_winrate_or_negative_expectancy")
        if max_dd > 12.0:
            threshold += 2.0
            liquidity_w += 1.0
            volatility_w += 1.0
            rationale.append("tighten_rules_due_to_drawdown")
        if win_rate >= 60.0 and expectancy > 0 and max_dd < 8.0:
            threshold -= 1.0
            trend_w += 1.0
            momentum_w += 1.0
            rationale.append("mild_expansion_due_to_strong_regime")

        updates = {
            "MIN_TOTAL_SCORE_TO_CANDIDATE": round(_clamp(threshold, 0.0, 100.0), 4),
            "ENABLE_SIGNAL_SCORE_GATE": "true",
            "SCORE_WEIGHT_TREND": round(_clamp(trend_w, 0.0, 100.0), 4),
            "SCORE_WEIGHT_MOMENTUM": round(_clamp(momentum_w, 0.0, 100.0), 4),
            "SCORE_WEIGHT_VOLATILITY": round(_clamp(volatility_w, 0.0, 100.0), 4),
            "SCORE_WEIGHT_LIQUIDITY": round(_clamp(liquidity_w, 0.0, 100.0), 4),
            "SCORE_WEIGHT_STRUCTURE": round(_clamp(structure_w, 0.0, 100.0), 4),
            "SCORE_WEIGHT_PORTFOLIO": round(_clamp(portfolio_w, 0.0, 100.0), 4),
        }
        updates = self._normalize_weights(updates)

        return {
            "generated_at": _utc_now_iso(),
            "sample_size": int(sample_size),
            "summary": {
                "win_rate": round(win_rate, 4),
                "expectancy": round(expectancy, 6),
                "max_drawdown_pct": round(max_dd, 6),
            },
            "proposed_updates": updates,
            "rationale": rationale or ["maintain_baseline_weights_with_safety_gate"],
        }

    def validate_proposal(
        self,
        proposal_payload: Dict[str, Any],
        config_map: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        cfg = config_map or self._fetch_config_map()
        findings: List[Dict[str, Any]] = []
        proposed = proposal_payload.get("proposed_updates") if isinstance(proposal_payload, dict) else {}
        if not isinstance(proposed, dict):
            proposed = {}

        min_sample_size = int(_to_float(cfg.get("PHASE3_MIN_SAMPLE_SIZE"), default=50))
        max_allowed_dd = _to_float(cfg.get("PHASE3_MAX_ALLOWED_DRAWDOWN"), default=20.0)
        sample_size = int(_to_float(proposal_payload.get("sample_size"), default=0))
        summary = proposal_payload.get("summary") if isinstance(proposal_payload, dict) else {}
        max_drawdown = _to_float((summary or {}).get("max_drawdown_pct"), default=0.0)

        if sample_size < min_sample_size:
            findings.append(
                {
                    "passed": False,
                    "severity": "ERROR",
                    "rule_code": "MIN_SAMPLE_SIZE",
                    "message": f"sample_size {sample_size} below required {min_sample_size}",
                    "details": {"sample_size": sample_size, "required": min_sample_size},
                }
            )

        if max_drawdown > max_allowed_dd:
            findings.append(
                {
                    "passed": False,
                    "severity": "ERROR",
                    "rule_code": "MAX_DRAWDOWN_GUARD",
                    "message": f"max_drawdown_pct {max_drawdown:.2f} exceeds {max_allowed_dd:.2f}",
                    "details": {"max_drawdown_pct": max_drawdown, "max_allowed_drawdown": max_allowed_dd},
                }
            )

        bounds = self._config_bounds()
        for key, value in proposed.items():
            if key not in self._ALLOWED_KEYS:
                findings.append(
                    {
                        "passed": False,
                        "severity": "ERROR",
                        "rule_code": "KEY_NOT_ALLOWED",
                        "message": f"{key} is not allowed for tuning proposal",
                        "details": {"key": key},
                    }
                )
                continue
            if key in bounds:
                lower, upper = bounds[key]
                numeric_value = _to_float(value, default=lower - 1)
                if numeric_value < lower or numeric_value > upper:
                    findings.append(
                        {
                            "passed": False,
                            "severity": "ERROR",
                            "rule_code": "VALUE_OUT_OF_BOUNDS",
                            "message": f"{key}={numeric_value} outside [{lower}, {upper}]",
                            "details": {"key": key, "value": numeric_value, "lower": lower, "upper": upper},
                        }
                    )

        # Weight sanity: avoid collapse to near-zero totals
        weight_total = sum(
            _to_float(proposed.get(key), default=0.0)
            for key in proposed.keys()
            if key.startswith("SCORE_WEIGHT_")
        )
        if weight_total > 0 and (weight_total < 80.0 or weight_total > 140.0):
            findings.append(
                {
                    "passed": False,
                    "severity": "WARN",
                    "rule_code": "WEIGHT_TOTAL_DRIFT",
                    "message": f"weight total {weight_total:.2f} is outside recommended [80, 140]",
                    "details": {"weight_total": weight_total},
                }
            )

        if not findings:
            findings.append(
                {
                    "passed": True,
                    "severity": "INFO",
                    "rule_code": "VALIDATION_OK",
                    "message": "proposal passed deterministic validation",
                    "details": {},
                }
            )

        hard_fail = any((not bool(item.get("passed"))) and str(item.get("severity", "")).upper() == "ERROR" for item in findings)
        if hard_fail:
            increment_counter("phase3_validation_reject_count", 1)
        return (not hard_fail), findings

    def create_proposal_for_walk_forward_run(
        self,
        walk_forward_run_id: str,
        proposed_by: str = "AI_ADVISOR",
    ) -> Dict[str, Any]:
        run_row = self.tracker.get_walk_forward_run_by_id(walk_forward_run_id)
        if not run_row:
            return {"ok": False, "error": "walk_forward_run_not_found"}

        metrics_summary = run_row.get("metrics_json") if isinstance(run_row.get("metrics_json"), dict) else {}
        sample_size = int(_to_float(run_row.get("sample_size"), default=0))
        config_snapshot = self._fetch_config_map()
        proposal_payload = self.build_proposal_payload(
            metrics_summary=metrics_summary or {},
            sample_size=sample_size,
            current_config=config_snapshot,
        )

        proposal_insert = self.tracker.track_tuning_proposal(
            status="DRAFT",
            proposal_payload=proposal_payload,
            walk_forward_run_id=walk_forward_run_id,
            proposed_by=proposed_by,
            config_snapshot=config_snapshot,
            config_hash=_stable_hash(config_snapshot),
            notes="phase3 advisor proposal generated",
        )
        if not proposal_insert.get("ok"):
            return {"ok": False, "error": proposal_insert.get("error", "proposal_insert_failed")}

        proposal_id = (proposal_insert.get("row") or {}).get("id")
        if not proposal_id:
            return {"ok": False, "error": "proposal_id_missing"}

        valid, findings = self.validate_proposal(
            proposal_payload=proposal_payload,
            config_map=config_snapshot,
        )
        for finding in findings:
            self.tracker.track_tuning_proposal_validation(
                tuning_proposal_id=proposal_id,
                validator="DETERMINISTIC_GUARD",
                passed=bool(finding.get("passed")),
                severity=str(finding.get("severity") or "ERROR"),
                rule_code=str(finding.get("rule_code") or ""),
                message=str(finding.get("message") or ""),
                details=finding.get("details") if isinstance(finding.get("details"), dict) else {},
            )

        self.tracker.update_tuning_proposal(
            tuning_proposal_id=proposal_id,
            status="VALIDATED" if valid else "REJECTED",
            notes="validated" if valid else "rejected by deterministic guards",
        )

        return {
            "ok": True,
            "tuning_proposal_id": proposal_id,
            "status": "VALIDATED" if valid else "REJECTED",
            "proposal_payload": proposal_payload,
            "validations": findings,
        }

    def transition_proposal_status(
        self,
        tuning_proposal_id: str,
        target_status: str,
        actor: str = "operator",
    ) -> Dict[str, Any]:
        proposal = self.tracker.get_tuning_proposal_by_id(tuning_proposal_id)
        if not proposal:
            return {"ok": False, "error": "proposal_not_found"}

        current_status = str(proposal.get("status") or "DRAFT").upper()
        target = str(target_status or "").upper()
        allowed = self._ALLOWED_TRANSITIONS.get(current_status, set())
        if target not in allowed:
            return {
                "ok": False,
                "error": "invalid_status_transition",
                "details": {"current_status": current_status, "target_status": target, "allowed": sorted(allowed)},
            }

        note = f"{current_status}->{target} by {actor} at {_utc_now_iso()}"
        result = self.tracker.update_tuning_proposal(
            tuning_proposal_id=tuning_proposal_id,
            status=target,
            notes=note,
        )
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error", "status_update_failed")}
        return {"ok": True, "status": target, "note": note}

    def apply_proposal(
        self,
        tuning_proposal_id: str,
        actor: str = "operator",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        proposal = self.tracker.get_tuning_proposal_by_id(tuning_proposal_id)
        if not proposal:
            return {"ok": False, "error": "proposal_not_found"}

        status = str(proposal.get("status") or "DRAFT").upper()
        if status != "APPROVED_MANUAL":
            return {"ok": False, "error": "proposal_not_manually_approved", "status": status}

        payload = proposal.get("proposal_payload") if isinstance(proposal.get("proposal_payload"), dict) else {}
        updates = payload.get("proposed_updates") if isinstance(payload.get("proposed_updates"), dict) else {}
        safe_updates = {key: value for key, value in updates.items() if key in self._ALLOWED_KEYS}

        if not dry_run and self.db:
            for key, value in safe_updates.items():
                self.db.table("bot_config").upsert({"key": key, "value": str(value)}).execute()

        next_status = "APPROVED_MANUAL" if dry_run else "APPLIED"
        note = f"{'dry-run' if dry_run else 'applied'} by {actor} at {_utc_now_iso()}"
        if not dry_run:
            self.tracker.update_tuning_proposal(
                tuning_proposal_id=tuning_proposal_id,
                status=next_status,
                notes=note,
            )
        return {
            "ok": True,
            "status": next_status,
            "applied_keys": sorted(safe_updates.keys()),
            "dry_run": dry_run,
        }

