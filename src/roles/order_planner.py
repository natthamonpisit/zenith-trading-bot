from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.database import get_db


def _to_float(raw: Any, default: float = 0.0) -> float:
    try:
        if raw is None:
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def _clean_cfg(raw: Any, default: str = "") -> str:
    if raw is None:
        return default
    return str(raw).replace('"', "").strip()


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


@dataclass
class OrderPlanConfig:
    order_plan_enabled: bool = True
    stop_loss_atr_multiplier: float = 1.8
    min_stop_loss_pct: float = 0.8
    tp1_r_multiple: float = 1.0
    tp2_r_multiple: float = 2.0
    tp1_partial_pct: float = 50.0
    breakeven_buffer_pct: float = 0.1
    trailing_mode: str = "ATR"
    trailing_atr_multiplier: float = 2.0
    trailing_pct: float = 3.0

    @classmethod
    def from_map(cls, cfg_map: Dict[str, Any]) -> "OrderPlanConfig":
        enabled = _clean_cfg(cfg_map.get("ORDER_PLAN_ENABLED"), default="true").lower() in {"1", "true", "yes", "on"}
        trailing_mode = _clean_cfg(cfg_map.get("ORDER_PLAN_TRAILING_MODE"), default="ATR").upper()
        if trailing_mode not in {"ATR", "PERCENT", "NONE"}:
            trailing_mode = "ATR"
        return cls(
            order_plan_enabled=enabled,
            stop_loss_atr_multiplier=_clamp(_to_float(cfg_map.get("STOP_LOSS_ATR_MULTIPLIER"), default=1.8), 0.5, 10.0),
            min_stop_loss_pct=_clamp(_to_float(cfg_map.get("MIN_STOP_LOSS_PCT"), default=0.8), 0.1, 10.0),
            tp1_r_multiple=_clamp(_to_float(cfg_map.get("TP1_R_MULTIPLE"), default=1.0), 0.5, 5.0),
            tp2_r_multiple=_clamp(_to_float(cfg_map.get("TP2_R_MULTIPLE"), default=2.0), 1.0, 10.0),
            tp1_partial_pct=_clamp(_to_float(cfg_map.get("TP1_PARTIAL_PCT"), default=50.0), 5.0, 95.0),
            breakeven_buffer_pct=_clamp(_to_float(cfg_map.get("BREAKEVEN_BUFFER_PCT"), default=0.1), 0.0, 1.0),
            trailing_mode=trailing_mode,
            trailing_atr_multiplier=_clamp(
                _to_float(cfg_map.get("TRAILING_STOP_ATR_MULTIPLIER"), default=2.0), 0.5, 10.0
            ),
            trailing_pct=_clamp(_to_float(cfg_map.get("TRAILING_STOP_PCT"), default=3.0), 0.2, 20.0),
        )


class OrderPlanner:
    """
    Deterministic order planning:
    - Entry
    - Initial SL
    - TP1 (partial), TP2 (full)
    - Breakeven promotion level
    """

    def __init__(self, db: Any = None):
        self.db = db or get_db()

    def _fetch_config_map(self) -> Dict[str, Any]:
        if not self.db:
            return {}
        try:
            rows = self.db.table("bot_config").select("key,value").execute().data or []
            return {str(row.get("key", "")): _clean_cfg(row.get("value")) for row in rows}
        except Exception:
            return {}

    def load_config(self) -> OrderPlanConfig:
        return OrderPlanConfig.from_map(self._fetch_config_map())

    def build_plan(
        self,
        symbol: str,
        side: str,
        timeframe: str,
        entry_price: float,
        tech_data: Dict[str, Any],
        run_id: str,
        asset_id: Optional[str] = None,
        score_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cfg = self.load_config()
        side_upper = str(side or "BUY").upper()
        entry = max(0.0, _to_float(entry_price, default=0.0))
        atr = max(0.0, _to_float(tech_data.get("atr"), default=0.0))
        if entry <= 0:
            raise ValueError(f"invalid entry_price for order plan: {entry_price}")

        min_stop_distance = entry * (cfg.min_stop_loss_pct / 100.0)
        atr_stop_distance = atr * cfg.stop_loss_atr_multiplier if atr > 0 else 0.0
        stop_distance = max(min_stop_distance, atr_stop_distance, entry * 0.001)

        if side_upper == "BUY":
            stop_loss = max(0.0, entry - stop_distance)
            risk_per_unit = max(0.0, entry - stop_loss)
            take_profit_1 = entry + (risk_per_unit * cfg.tp1_r_multiple)
            take_profit_2 = entry + (risk_per_unit * cfg.tp2_r_multiple)
            breakeven_price = entry * (1.0 + (cfg.breakeven_buffer_pct / 100.0))
        else:
            stop_loss = entry + stop_distance
            risk_per_unit = max(0.0, stop_loss - entry)
            take_profit_1 = entry - (risk_per_unit * cfg.tp1_r_multiple)
            take_profit_2 = entry - (risk_per_unit * cfg.tp2_r_multiple)
            breakeven_price = entry * (1.0 - (cfg.breakeven_buffer_pct / 100.0))

        return {
            "run_id": str(run_id),
            "asset_id": asset_id,
            "symbol": str(symbol).upper().strip(),
            "side": side_upper,
            "timeframe": str(timeframe),
            "entry_price": round(entry, 8),
            "stop_loss": round(stop_loss, 8),
            "take_profit_1": round(take_profit_1, 8),
            "take_profit_2": round(take_profit_2, 8),
            "risk_per_unit": round(risk_per_unit, 8),
            "tp1_partial_pct": round(cfg.tp1_partial_pct, 4),
            "breakeven_price": round(breakeven_price, 8),
            "trailing_mode": cfg.trailing_mode,
            "trailing_value": round(
                cfg.trailing_atr_multiplier if cfg.trailing_mode == "ATR" else cfg.trailing_pct, 8
            ),
            "status": "PLANNED",
            "plan_payload": {
                "config": {
                    "order_plan_enabled": cfg.order_plan_enabled,
                    "stop_loss_atr_multiplier": cfg.stop_loss_atr_multiplier,
                    "min_stop_loss_pct": cfg.min_stop_loss_pct,
                    "tp1_r_multiple": cfg.tp1_r_multiple,
                    "tp2_r_multiple": cfg.tp2_r_multiple,
                    "tp1_partial_pct": cfg.tp1_partial_pct,
                    "breakeven_buffer_pct": cfg.breakeven_buffer_pct,
                    "trailing_mode": cfg.trailing_mode,
                    "trailing_atr_multiplier": cfg.trailing_atr_multiplier,
                    "trailing_pct": cfg.trailing_pct,
                },
                "score": score_result or {},
                "tech": {
                    "atr": _to_float(tech_data.get("atr"), default=0.0),
                    "rsi": _to_float(tech_data.get("rsi"), default=0.0),
                    "adx": _to_float(tech_data.get("adx"), default=0.0),
                },
            },
        }

    def persist_plan(self, plan_payload: Dict[str, Any]) -> Optional[str]:
        if not self.db:
            return None
        try:
            row = self.db.table("order_plans").insert(plan_payload).execute().data or []
            if row:
                return row[0].get("id")
        except Exception:
            return None
        return None

    def update_plan(self, order_plan_id: Optional[str], **fields: Any) -> None:
        if not self.db or not order_plan_id:
            return
        payload = {key: value for key, value in fields.items() if value is not None}
        if not payload:
            return
        try:
            self.db.table("order_plans").update(payload).eq("id", order_plan_id).execute()
        except Exception:
            pass
