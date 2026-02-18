"""
P5 AI tiering pipeline with token-efficient summarization.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional, Tuple


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _estimate_tokens(payload: Any) -> int:
    # Rough estimate: ~4 chars/token.
    return max(1, len(str(payload)) // 4)


def _latest_column_value(snapshot: Dict[str, Any], key: str, default: float = 0.0) -> float:
    series = snapshot.get(key)
    if isinstance(series, dict) and series:
        last_key = sorted(series.keys())[-1]
        return _safe_float(series.get(last_key), default=default)
    if isinstance(series, list) and series:
        return _safe_float(series[-1], default=default)
    return _safe_float(series, default=default)


class TieredAIDecisionEngine:
    """
    Tier-1: summarizer (deterministic compact market view)
    Tier-2: model decision
    Tier-3: governor (safety + policy normalization)
    """

    def __init__(self, strategist: Optional[Any] = None):
        self.strategist = strategist

    def tier_1_summarize(self, symbol: str, tech_snapshot: Dict[str, Any], intent: str = "ENTRY") -> Dict[str, Any]:
        close = _latest_column_value(tech_snapshot, "close")
        rsi = _latest_column_value(tech_snapshot, "rsi", default=50.0)
        macd = _latest_column_value(tech_snapshot, "macd")
        macd_signal = _latest_column_value(tech_snapshot, "signal")
        ema_20 = _latest_column_value(tech_snapshot, "ema_20")
        ema_50 = _latest_column_value(tech_snapshot, "ema_50")
        ema_200 = _latest_column_value(tech_snapshot, "ema_200")
        atr = _latest_column_value(tech_snapshot, "atr")
        volume = _latest_column_value(tech_snapshot, "volume")

        trend_bias = "NEUTRAL"
        if close > ema_50 > ema_200:
            trend_bias = "BULLISH"
        elif close < ema_50 < ema_200:
            trend_bias = "BEARISH"

        momentum_bias = "BULLISH" if macd >= macd_signal else "BEARISH"

        summary = {
            "symbol": symbol,
            "intent": intent,
            "price": round(close, 8),
            "rsi": round(rsi, 4),
            "macd": round(macd, 8),
            "macd_signal": round(macd_signal, 8),
            "ema_20": round(ema_20, 8),
            "ema_50": round(ema_50, 8),
            "ema_200": round(ema_200, 8),
            "atr": round(atr, 8),
            "volume": round(volume, 8),
            "trend_bias": trend_bias,
            "momentum_bias": momentum_bias,
            "token_estimate": _estimate_tokens(tech_snapshot),
        }
        return summary

    def tier_2_decide(self, symbol: str, summary: Dict[str, Any], intent: str = "ENTRY") -> Dict[str, Any]:
        if not self.strategist:
            return {
                "recommendation": "WAIT" if intent == "ENTRY" else "HOLD",
                "confidence": 0,
                "sentiment_score": 0.0,
                "reasoning": "Strategist unavailable",
                "model": "NONE",
            }

        raw = self.strategist.analyze_market(
            snapshot_id=None,
            asset_symbol=symbol,
            tech_data=summary,
            intent=intent,
        )

        recommendation = str((raw or {}).get("recommendation", "WAIT")).upper()
        confidence = _safe_float((raw or {}).get("confidence"), default=0.0)
        sentiment = _safe_float((raw or {}).get("sentiment_score"), default=0.0)
        reasoning = str((raw or {}).get("reasoning", ""))

        return {
            "recommendation": recommendation,
            "confidence": max(0.0, min(100.0, confidence)),
            "sentiment_score": max(-1.0, min(1.0, sentiment)),
            "reasoning": reasoning,
            "model": getattr(getattr(self.strategist, "model", None), "model_name", "GEMINI"),
        }

    def tier_3_govern(
        self,
        tier_2: Dict[str, Any],
        intent: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cfg = config or {}
        min_conf = _safe_float(cfg.get("AI_CONF_THRESHOLD"), default=60.0)

        recommendation = str(tier_2.get("recommendation", "WAIT")).upper()
        confidence = _safe_float(tier_2.get("confidence"), default=0.0)
        reasoning = str(tier_2.get("reasoning", ""))
        sentiment = _safe_float(tier_2.get("sentiment_score"), default=0.0)

        veto_reasons = []
        allowed = {"ENTRY": {"BUY", "WAIT"}, "EXIT": {"SELL", "HOLD"}}.get(intent, {"WAIT"})
        if recommendation not in allowed:
            veto_reasons.append("RECOMMENDATION_OUT_OF_INTENT")
            recommendation = "WAIT" if intent == "ENTRY" else "HOLD"

        actionable = recommendation in {"BUY", "SELL"}
        if actionable and confidence < min_conf:
            veto_reasons.append("LOW_CONFIDENCE")
            recommendation = "WAIT" if intent == "ENTRY" else "HOLD"

        return {
            "recommendation": recommendation,
            "confidence": confidence,
            "sentiment_score": sentiment,
            "reasoning": reasoning,
            "veto_reasons": veto_reasons,
            "governor_passed": len(veto_reasons) == 0,
        }

    def evaluate(
        self,
        symbol: str,
        tech_snapshot: Dict[str, Any],
        intent: str = "ENTRY",
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        run_id = str(uuid.uuid4())

        t1_start = time.perf_counter()
        summary = self.tier_1_summarize(symbol=symbol, tech_snapshot=tech_snapshot, intent=intent)
        t1_latency = int((time.perf_counter() - t1_start) * 1000)

        t2_start = time.perf_counter()
        tier_2 = self.tier_2_decide(symbol=symbol, summary=summary, intent=intent)
        t2_latency = int((time.perf_counter() - t2_start) * 1000)

        t3_start = time.perf_counter()
        governor = self.tier_3_govern(tier_2=tier_2, intent=intent, config=config)
        t3_latency = int((time.perf_counter() - t3_start) * 1000)

        return {
            "run_id": run_id,
            "tier_1": {"summary": summary, "latency_ms": t1_latency},
            "tier_2": {"decision": tier_2, "latency_ms": t2_latency},
            "tier_3": {"governor": governor, "latency_ms": t3_latency},
            "final": {
                "recommendation": governor["recommendation"],
                "confidence": governor["confidence"],
                "sentiment_score": governor["sentiment_score"],
                "reasoning": governor["reasoning"],
            },
            "token_efficiency": {
                "tier_1_prompt_tokens": summary.get("token_estimate", 0),
                "tier_2_prompt_tokens": _estimate_tokens(summary),
                "total_estimated_tokens": summary.get("token_estimate", 0) + _estimate_tokens(summary),
            },
        }

    def to_telemetry_records(self, result: Dict[str, Any], symbol: str, timeframe: str) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        """
        Convert evaluate() output into 3 telemetry rows for ai_decisions.
        """
        run_id = result["run_id"]
        t1_summary = result["tier_1"]["summary"]
        t2_decision = result["tier_2"]["decision"]
        t3_governor = result["tier_3"]["governor"]

        tier_1 = {
            "run_id": run_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "tier": "TIER_1_SUMMARIZER",
            "model": "DETERMINISTIC",
            "prompt": {"type": "summary"},
            "input_payload": t1_summary,
            "output_json": t1_summary,
            "confidence": t2_decision.get("confidence", 0.0),
            "latency_ms": result["tier_1"]["latency_ms"],
        }

        tier_2 = {
            "run_id": run_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "tier": "TIER_2_DECISION",
            "model": t2_decision.get("model", "GEMINI"),
            "prompt": {"type": "decision"},
            "input_payload": t1_summary,
            "output_json": t2_decision,
            "confidence": t2_decision.get("confidence", 0.0),
            "latency_ms": result["tier_2"]["latency_ms"],
        }

        tier_3 = {
            "run_id": run_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "tier": "TIER_3_GOVERNOR",
            "model": "RULE_GOVERNOR",
            "prompt": {"type": "governor"},
            "input_payload": t2_decision,
            "output_json": t3_governor,
            "confidence": t3_governor.get("confidence", 0.0),
            "latency_ms": result["tier_3"]["latency_ms"],
        }

        return tier_1, tier_2, tier_3
