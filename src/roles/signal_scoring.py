from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.database import get_db


def _clean_cfg_value(raw: Any, default: str = "") -> str:
    if raw is None:
        return default
    return str(raw).replace('"', "").strip()


def _to_float(raw: Any, default: float = 0.0) -> float:
    try:
        if raw is None:
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def _to_bool(raw: Any, default: bool = False) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _bounded_float(config_map: Dict[str, Any], key: str, default: float, lower: float, upper: float) -> float:
    value = _to_float(config_map.get(key), default=default)
    return _clamp(value, lower, upper)


@dataclass
class ScoreConfig:
    min_total_score: float = 60.0
    enable_score_gate: bool = False
    liquidity_min_volume: float = 10000.0
    weight_trend: float = 25.0
    weight_momentum: float = 20.0
    weight_volatility: float = 15.0
    weight_liquidity: float = 20.0
    weight_structure: float = 10.0
    weight_portfolio: float = 10.0

    @classmethod
    def from_map(cls, config_map: Dict[str, Any]) -> "ScoreConfig":
        min_volume = _to_float(config_map.get("SCORE_LIQUIDITY_MIN_VOLUME"), default=-1.0)
        if min_volume <= 0:
            min_volume = _to_float(config_map.get("MIN_VOLUME"), default=10000.0)

        threshold = _to_float(config_map.get("MIN_TOTAL_SCORE_TO_CANDIDATE"), default=-1.0)
        if threshold < 0:
            threshold = _to_float(config_map.get("SCORE_THRESHOLD_CANDIDATE"), default=60.0)

        return cls(
            min_total_score=_clamp(threshold, 0.0, 100.0),
            enable_score_gate=_to_bool(config_map.get("ENABLE_SIGNAL_SCORE_GATE"), default=False),
            liquidity_min_volume=max(1.0, min_volume),
            weight_trend=_bounded_float(config_map, "SCORE_WEIGHT_TREND", default=25.0, lower=0.0, upper=100.0),
            weight_momentum=_bounded_float(config_map, "SCORE_WEIGHT_MOMENTUM", default=20.0, lower=0.0, upper=100.0),
            weight_volatility=_bounded_float(config_map, "SCORE_WEIGHT_VOLATILITY", default=15.0, lower=0.0, upper=100.0),
            weight_liquidity=_bounded_float(config_map, "SCORE_WEIGHT_LIQUIDITY", default=20.0, lower=0.0, upper=100.0),
            weight_structure=_bounded_float(config_map, "SCORE_WEIGHT_STRUCTURE", default=10.0, lower=0.0, upper=100.0),
            weight_portfolio=_bounded_float(config_map, "SCORE_WEIGHT_PORTFOLIO", default=10.0, lower=0.0, upper=100.0),
        )

    def weights(self) -> Dict[str, float]:
        return {
            "trend": self.weight_trend,
            "momentum": self.weight_momentum,
            "volatility": self.weight_volatility,
            "liquidity": self.weight_liquidity,
            "structure": self.weight_structure,
            "portfolio": self.weight_portfolio,
        }


@dataclass
class ScoreResult:
    total_score: float
    threshold: float
    passed_threshold: bool
    score_gate_enabled: bool
    component_scores: Dict[str, float]
    weighted_scores: Dict[str, float]
    weights: Dict[str, float]
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_score": self.total_score,
            "threshold": self.threshold,
            "passed_threshold": self.passed_threshold,
            "score_gate_enabled": self.score_gate_enabled,
            "component_scores": self.component_scores,
            "weighted_scores": self.weighted_scores,
            "weights": self.weights,
            "notes": self.notes,
        }


def _score_trend(tech_data: Dict[str, Any]) -> Tuple[float, List[str]]:
    notes: List[str] = []
    close = _to_float(tech_data.get("close"))
    ema_20 = _to_float(tech_data.get("ema_20"))
    ema_50 = _to_float(tech_data.get("ema_50"))
    ema_200 = _to_float(tech_data.get("ema_200"))
    adx = _to_float(tech_data.get("adx"))
    trend_info = tech_data.get("market_trend") if isinstance(tech_data.get("market_trend"), dict) else {}

    ema_alignment = 0.35
    if close > 0 and ema_200 > 0 and close > ema_200:
        ema_alignment = 0.55
    if close > 0 and ema_50 > 0 and ema_200 > 0 and close > ema_50 > ema_200:
        ema_alignment = 0.75
    if close > 0 and ema_20 > 0 and ema_50 > 0 and ema_200 > 0 and close > ema_20 > ema_50 > ema_200:
        ema_alignment = 0.95
    if close > 0 and ema_20 > 0 and ema_50 > 0 and ema_200 > 0 and close < ema_20 < ema_50 < ema_200:
        ema_alignment = 0.08

    trend_hint_map = {
        "STRONG_UPTREND": 0.95,
        "UPTREND": 0.75,
        "NEUTRAL": 0.50,
        "DOWNTREND": 0.25,
        "STRONG_DOWNTREND": 0.08,
    }
    trend_hint = trend_hint_map.get(str(trend_info.get("trend", "")).upper())
    if trend_hint is not None:
        ema_alignment = (ema_alignment + trend_hint) / 2.0
        notes.append(f"market_trend={str(trend_info.get('trend', 'UNKNOWN')).upper()}")

    adx_norm = _clamp(adx / 35.0, 0.0, 1.0)
    score = 100.0 * ((ema_alignment * 0.7) + (adx_norm * 0.3))
    return _clamp(score, 0.0, 100.0), notes


def _score_momentum(tech_data: Dict[str, Any]) -> Tuple[float, List[str]]:
    notes: List[str] = []
    rsi = _to_float(tech_data.get("rsi"), default=50.0)
    macd = _to_float(tech_data.get("macd"), default=0.0)
    signal = _to_float(tech_data.get("macd_signal", tech_data.get("signal")), default=0.0)

    if rsi < 30:
        rsi_score = 35.0
        notes.append("rsi_oversold")
    elif rsi < 45:
        rsi_score = 55.0 + ((rsi - 30.0) * 1.5)
    elif rsi <= 65:
        rsi_score = 95.0 - (abs(rsi - 55.0) * 1.5)
    elif rsi <= 75:
        rsi_score = 80.0 - ((rsi - 65.0) * 3.0)
    else:
        rsi_score = max(10.0, 50.0 - ((rsi - 75.0) * 2.5))
        notes.append("rsi_overbought")

    if macd == 0 and signal == 0:
        macd_score = 50.0
    else:
        denominator = max(abs(macd), abs(signal), 1e-6)
        ratio = (macd - signal) / denominator
        macd_score = _clamp(50.0 + (ratio * 35.0), 0.0, 100.0)

    score = (rsi_score * 0.55) + (macd_score * 0.45)
    return _clamp(score, 0.0, 100.0), notes


def _score_volatility(tech_data: Dict[str, Any]) -> Tuple[float, List[str]]:
    notes: List[str] = []
    close = _to_float(tech_data.get("close"))
    atr = _to_float(tech_data.get("atr"))
    bb_upper = _to_float(tech_data.get("bb_upper"))
    bb_lower = _to_float(tech_data.get("bb_lower"))

    atr_score = 50.0
    if close > 0 and atr > 0:
        atr_pct = (atr / close) * 100.0
        atr_score = _clamp(100.0 - (abs(atr_pct - 1.8) * 28.0), 10.0, 100.0)
        if atr_pct < 0.25:
            atr_score = min(atr_score, 25.0)
            notes.append("volatility_too_low")
        elif atr_pct > 8.0:
            atr_score = min(atr_score, 25.0)
            notes.append("volatility_too_high")

    bb_score = 55.0
    if bb_upper > bb_lower and close > 0:
        width_pct = ((bb_upper - bb_lower) / close) * 100.0
        bb_score = _clamp(100.0 - (abs(width_pct - 4.5) * 16.0), 10.0, 100.0)

    score = (atr_score * 0.65) + (bb_score * 0.35)
    return _clamp(score, 0.0, 100.0), notes


def _score_liquidity(
    tech_data: Dict[str, Any],
    candidate_meta: Optional[Dict[str, Any]],
    config: ScoreConfig,
) -> Tuple[float, List[str]]:
    notes: List[str] = []
    meta = candidate_meta or {}
    close = _to_float(tech_data.get("close"), default=0.0)
    base_volume = _to_float(tech_data.get("volume"), default=0.0)

    quote_volume = _to_float(meta.get("quote_volume"), default=0.0)
    if quote_volume <= 0 and close > 0 and base_volume > 0:
        quote_volume = close * base_volume

    min_volume = max(1.0, _to_float(config.liquidity_min_volume, default=10000.0))
    ratio = quote_volume / min_volume
    volume_score = _clamp(ratio * 50.0, 0.0, 100.0)

    if ratio < 1.0:
        notes.append(f"low_liquidity_ratio={ratio:.2f}")

    spread_bps = _to_float(meta.get("spread_bps"), default=-1.0)
    if spread_bps < 0:
        spread_score = 60.0
    else:
        spread_score = _clamp(100.0 - (spread_bps * 1.8), 5.0, 100.0)
        if spread_bps > 25:
            notes.append(f"wide_spread_bps={spread_bps:.1f}")

    score = (volume_score * 0.80) + (spread_score * 0.20)
    return _clamp(score, 0.0, 100.0), notes


def _score_structure(tech_data: Dict[str, Any]) -> Tuple[float, List[str]]:
    notes: List[str] = []
    close = _to_float(tech_data.get("close"), default=0.0)
    ema_20 = _to_float(tech_data.get("ema_20"), default=0.0)
    ema_50 = _to_float(tech_data.get("ema_50"), default=0.0)
    price_position = _to_float(tech_data.get("price_position_score"), default=1.5)

    position_score = _clamp((price_position / 3.0) * 100.0, 0.0, 100.0)

    ema_context = 50.0
    if close > 0 and ema_20 > 0 and ema_50 > 0:
        if close >= ema_20 >= ema_50:
            ema_context = 92.0
        elif close >= ema_50:
            ema_context = 70.0
        elif close >= (ema_50 * 0.98):
            ema_context = 55.0
        else:
            ema_context = 25.0
            notes.append("price_below_structure")

    score = (position_score * 0.70) + (ema_context * 0.30)
    return _clamp(score, 0.0, 100.0), notes


def _score_portfolio(
    ai_data: Optional[Dict[str, Any]],
    candidate_meta: Optional[Dict[str, Any]],
) -> Tuple[float, List[str]]:
    notes: List[str] = []
    ai = ai_data or {}
    meta = candidate_meta or {}

    ai_conf = _clamp(_to_float(ai.get("confidence"), default=50.0), 0.0, 100.0)
    sentiment = _clamp(_to_float(ai.get("sentiment_score"), default=0.0), -1.0, 1.0)
    sentiment_score = (sentiment + 1.0) * 50.0

    correlation_penalty = _clamp(_to_float(meta.get("correlation_penalty"), default=0.0), 0.0, 40.0)
    if correlation_penalty > 0:
        notes.append(f"correlation_penalty={correlation_penalty:.1f}")

    base = (ai_conf * 0.7) + (sentiment_score * 0.3)
    score = _clamp(base - correlation_penalty, 0.0, 100.0)
    return score, notes


def calculate_signal_score(
    tech_data: Dict[str, Any],
    ai_data: Optional[Dict[str, Any]] = None,
    candidate_meta: Optional[Dict[str, Any]] = None,
    config: Optional[ScoreConfig] = None,
) -> ScoreResult:
    cfg = config or ScoreConfig()
    trend_score, trend_notes = _score_trend(tech_data)
    momentum_score, momentum_notes = _score_momentum(tech_data)
    volatility_score, volatility_notes = _score_volatility(tech_data)
    liquidity_score, liquidity_notes = _score_liquidity(tech_data, candidate_meta, cfg)
    structure_score, structure_notes = _score_structure(tech_data)
    portfolio_score, portfolio_notes = _score_portfolio(ai_data, candidate_meta)

    component_scores = {
        "trend": round(trend_score, 4),
        "momentum": round(momentum_score, 4),
        "volatility": round(volatility_score, 4),
        "liquidity": round(liquidity_score, 4),
        "structure": round(structure_score, 4),
        "portfolio": round(portfolio_score, 4),
    }
    weights = cfg.weights()
    total_weight = sum(max(0.0, value) for value in weights.values())
    if total_weight <= 0:
        fallback = ScoreConfig()
        weights = fallback.weights()
        total_weight = sum(weights.values())

    weighted_scores: Dict[str, float] = {}
    total_score = 0.0
    for component, score in component_scores.items():
        weight = max(0.0, _to_float(weights.get(component), default=0.0))
        weighted = (score * weight) / total_weight
        total_score += weighted
        weighted_scores[component] = round(weighted, 4)

    notes = trend_notes + momentum_notes + volatility_notes + liquidity_notes + structure_notes + portfolio_notes
    total_score = round(_clamp(total_score, 0.0, 100.0), 2)
    threshold = round(_clamp(cfg.min_total_score, 0.0, 100.0), 2)

    return ScoreResult(
        total_score=total_score,
        threshold=threshold,
        passed_threshold=total_score >= threshold,
        score_gate_enabled=cfg.enable_score_gate,
        component_scores=component_scores,
        weighted_scores=weighted_scores,
        weights={key: round(_to_float(value, 0.0), 4) for key, value in weights.items()},
        notes=notes[:20],
    )


class SignalScorer:
    """
    Runtime scorer with lightweight config caching.
    """

    def __init__(self, db: Any = None, cache_ttl_sec: float = 30.0):
        self.db = db or get_db()
        self.cache_ttl_sec = max(5.0, _to_float(cache_ttl_sec, default=30.0))
        self._cached_config = ScoreConfig()
        self._last_loaded_ts = 0.0

    def _fetch_config_map(self) -> Dict[str, Any]:
        if not self.db:
            return {}
        try:
            rows = self.db.table("bot_config").select("key,value").execute().data or []
            return {str(row.get("key", "")): _clean_cfg_value(row.get("value")) for row in rows}
        except Exception:
            return {}

    def load_config(self, force: bool = False) -> ScoreConfig:
        now = time.time()
        if not force and (now - self._last_loaded_ts) < self.cache_ttl_sec:
            return self._cached_config
        cfg = ScoreConfig.from_map(self._fetch_config_map())
        self._cached_config = cfg
        self._last_loaded_ts = now
        return cfg

    def score(
        self,
        tech_data: Dict[str, Any],
        ai_data: Optional[Dict[str, Any]] = None,
        candidate_meta: Optional[Dict[str, Any]] = None,
    ) -> ScoreResult:
        config = self.load_config(force=False)
        return calculate_signal_score(
            tech_data=tech_data,
            ai_data=ai_data,
            candidate_meta=candidate_meta,
            config=config,
        )
