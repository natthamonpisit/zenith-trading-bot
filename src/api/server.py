"""
FastAPI backend for dashboard read APIs.
"""
from __future__ import annotations

import asyncio
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Query, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect
from starlette import status

from src.contracts.api_contracts import (
    CandidateDTO,
    KlineCandleDTO,
    KlineDTO,
    SignalDTO,
    SummaryDTO,
    WSEvent,
    build_error_response,
    build_success_response,
)
from src.contracts.error_codes import ErrorCode, build_api_error
from src.database import get_db
from src.ops.cutover import CutoverService
from src.ops.hardening import HardeningService, compare_dashboard_summary
from src.roles.job_analysis import Strategist
from src.roles.job_price import PriceSpy
from src.telemetry.tracker import TelemetryTracker
from src.utils.rate_limiter import RateLimiter

ALLOWED_TFS = {"1m", "5m", "15m", "1h", "4h", "1d"}
MAX_KLINES_LIMIT = 2000
DEFAULT_KLINES_LIMIT = 500
DEFAULT_WS_LIMIT = 200

WS_TOPIC_SUMMARY = "dashboard.summary"
WS_TOPIC_POSITIONS = "positions.updates"
WS_TOPIC_EVENTS = "system.events"
WS_CHART_TOPIC_PATTERN = re.compile(r"^chart\.kline\.([A-Za-z0-9/_-]+)\.([A-Za-z0-9]+)$")

_price_spy: Optional[PriceSpy] = None
_strategist: Optional[Strategist] = None
_client_limiters: Dict[str, RateLimiter] = {}


class APIRequestError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


def _json_success(data: Any, request_id: str, http_status: int = status.HTTP_200_OK) -> JSONResponse:
    payload = build_success_response(data=data, request_id=request_id)
    return JSONResponse(status_code=http_status, content=payload.model_dump(mode="json"))


def _json_error(
    code: ErrorCode,
    message: str,
    request_id: str,
    http_status: int,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    api_error = build_api_error(code=code, message=message, details=details)
    payload = build_error_response(error=api_error, request_id=request_id)
    return JSONResponse(status_code=http_status, content=payload.model_dump(mode="json"))


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


def _to_int(raw: Any, default: int = 0) -> int:
    try:
        if raw is None:
            return default
        return int(raw)
    except (TypeError, ValueError):
        return default


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


def _request_id_from(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def _validate_uuid_or_none(raw_value: Optional[str], field_name: str) -> Optional[str]:
    if not raw_value:
        return None
    try:
        return str(uuid.UUID(raw_value))
    except ValueError:
        raise APIRequestError(
            code=ErrorCode.E_VALIDATION_400,
            message=f"{field_name} must be a valid UUID",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={field_name: raw_value},
        )


def _extract_symbol(raw_row: Dict[str, Any]) -> str:
    asset_info = raw_row.get("assets")
    if isinstance(asset_info, dict):
        symbol = asset_info.get("symbol")
        if symbol:
            return str(symbol)
    return "UNKNOWN"


def _fetch_bot_config_value(db: Any, key: str) -> Optional[Any]:
    result = db.table("bot_config").select("value").eq("key", key).limit(1).execute()
    if result.data:
        return result.data[0].get("value")
    return None


def _probe_db_health(db: Any) -> bool:
    try:
        db.table("bot_config").select("key").limit(1).execute()
        return True
    except Exception:
        return False


def _resolve_mode(db: Any, requested_mode: Optional[str]) -> str:
    if requested_mode:
        mode = requested_mode.upper().strip()
        if mode not in {"PAPER", "LIVE"}:
            raise APIRequestError(
                code=ErrorCode.E_VALIDATION_400,
                message="mode must be PAPER or LIVE",
                status_code=status.HTTP_400_BAD_REQUEST,
                details={"mode": requested_mode},
            )
        return mode

    mode_raw = _fetch_bot_config_value(db, "TRADING_MODE")
    mode = _clean_cfg_value(mode_raw, default="PAPER").upper()
    return mode if mode in {"PAPER", "LIVE"} else "PAPER"


def _compute_summary(db: Any, mode: str) -> SummaryDTO:
    is_sim = mode == "PAPER"

    equity = 0.0
    if is_sim:
        try:
            sim_result = db.table("simulation_portfolio").select("balance").eq("id", 1).limit(1).execute()
            if sim_result.data:
                equity = _to_float(sim_result.data[0].get("balance"), default=0.0)
        except Exception:
            equity = 0.0
    else:
        try:
            session_result = (
                db.table("trading_sessions")
                .select("current_balance")
                .eq("mode", "LIVE")
                .eq("is_active", True)
                .order("started_at", desc=True)
                .limit(1)
                .execute()
            )
            if session_result.data:
                equity = _to_float(session_result.data[0].get("current_balance"), default=0.0)
        except Exception:
            equity = 0.0

    day_start_iso = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    daily_pnl = 0.0
    try:
        daily_result = (
            db.table("positions")
            .select("pnl")
            .eq("is_open", False)
            .eq("is_sim", is_sim)
            .gte("closed_at", day_start_iso)
            .execute()
        )
        if daily_result.data:
            daily_pnl = sum(_to_float(row.get("pnl"), default=0.0) for row in daily_result.data)
    except Exception:
        daily_pnl = 0.0

    open_positions = 0
    try:
        open_result = (
            db.table("positions")
            .select("id", count="exact")
            .eq("is_open", True)
            .eq("is_sim", is_sim)
            .limit(1)
            .execute()
        )
        open_positions = _to_int(getattr(open_result, "count", 0), default=0)
    except Exception:
        open_positions = 0

    win_rate = 0.0
    try:
        closed_result = (
            db.table("positions")
            .select("pnl")
            .eq("is_open", False)
            .eq("is_sim", is_sim)
            .limit(1000)
            .execute()
        )
        pnl_values = []
        for row in closed_result.data or []:
            pnl = row.get("pnl")
            if pnl is not None:
                pnl_values.append(_to_float(pnl))
        if pnl_values:
            wins = len([value for value in pnl_values if value > 0])
            win_rate = round((wins / len(pnl_values)) * 100, 2)
    except Exception:
        win_rate = 0.0

    drawdown_pct = 0.0
    try:
        latest_dd = db.table("balance_snapshots").select("drawdown_pct").order("snapshot_at", desc=True).limit(1).execute()
        if latest_dd.data:
            drawdown_pct = _to_float(latest_dd.data[0].get("drawdown_pct"), default=0.0)
    except Exception:
        drawdown_pct = 0.0

    bot_status = _clean_cfg_value(_fetch_bot_config_value(db, "BOT_STATUS"), default="UNKNOWN").upper()
    if not bot_status:
        bot_status = "UNKNOWN"

    return SummaryDTO(
        equity=round(equity, 4),
        daily_pnl=round(daily_pnl, 4),
        drawdown_pct=round(drawdown_pct, 4),
        open_positions=open_positions,
        win_rate=round(win_rate, 2),
        bot_status=bot_status,
    )


def _compute_candidates(db: Any, limit: int) -> List[CandidateDTO]:
    rows: List[Dict[str, Any]] = []

    try:
        result = db.table("fundamental_coins").select("symbol,status,manual_score").order("manual_score", desc=True).limit(limit).execute()
        rows = result.data or []
    except Exception:
        rows = []

    if not rows:
        try:
            fallback = db.table("assets").select("symbol,status").eq("status", "active").limit(limit).execute()
            rows = fallback.data or []
        except Exception:
            rows = []

    candidates: List[CandidateDTO] = []
    for idx, row in enumerate(rows, start=1):
        symbol = str(row.get("symbol", "UNKNOWN")).upper()
        status_val = str(row.get("status", "NEUTRAL")).upper()
        manual_score = _to_float(row.get("manual_score"), default=5.0)
        liquidity_score = max(0.0, min(100.0, manual_score * 10.0))
        tradable = status_val != "BLACKLIST"
        reject_reason = None if tradable else "BLACKLISTED_BY_FUNDAMENTAL"

        candidates.append(
            CandidateDTO(
                symbol=symbol,
                screener_rank=idx,
                liquidity_score=round(liquidity_score, 2),
                tradable=tradable,
                reject_reason=reject_reason,
            )
        )

    return candidates


def _normalize_signal_type(raw_value: Any) -> Tuple[str, Optional[str]]:
    normalized = str(raw_value or "").upper().strip()
    if normalized in {"BUY", "SELL", "HOLD", "WAIT"}:
        return normalized, None
    if normalized == "REJECT":
        return "WAIT", "SIGNAL_REJECTED_BY_RULES"
    return "WAIT", "UNKNOWN_SIGNAL_TYPE"


def _extract_ai_confidence(raw_row: Dict[str, Any]) -> float:
    raw_ai = raw_row.get("ai_analysis")
    if isinstance(raw_ai, dict):
        return max(0.0, min(100.0, _to_float(raw_ai.get("ai_confidence"), default=0.0)))
    if isinstance(raw_ai, list) and raw_ai:
        first = raw_ai[0]
        if isinstance(first, dict):
            return max(0.0, min(100.0, _to_float(first.get("ai_confidence"), default=0.0)))
    return 0.0


def _compute_signals(
    db: Any,
    status_filter: Optional[str],
    symbol_filter: Optional[str],
    limit: int,
) -> List[SignalDTO]:
    query = (
        db.table("trade_signals")
        .select("id,signal_type,status,judge_reason,exit_reason,created_at,assets(symbol),ai_analysis(ai_confidence)")
        .order("created_at", desc=True)
        .limit(limit)
    )

    if status_filter:
        query = query.eq("status", status_filter.upper())

    rows = query.execute().data or []

    symbol_filter_norm = symbol_filter.upper() if symbol_filter else None
    signals: List[SignalDTO] = []

    for row in rows:
        symbol = _extract_symbol(row).upper()
        if symbol_filter_norm and symbol != symbol_filter_norm:
            continue

        signal_type, remap_code = _normalize_signal_type(row.get("signal_type"))
        reason_codes: List[str] = []
        if row.get("judge_reason"):
            reason_codes.append("JUDGE_REASON")
        if row.get("exit_reason"):
            reason_codes.append("EXIT_REASON")
        if remap_code:
            reason_codes.append(remap_code)

        signals.append(
            SignalDTO(
                id=str(row.get("id")),
                symbol=symbol,
                signal_type=signal_type,  # type: ignore[arg-type]
                confidence=_extract_ai_confidence(row),
                status=str(row.get("status") or "UNKNOWN").upper(),
                reason_codes=reason_codes,
            )
        )

    return signals


def _compute_positions(
    db: Any,
    is_open: Optional[bool],
    symbol_filter: Optional[str],
    session_id_filter: Optional[str],
    limit: int,
) -> List[Dict[str, Any]]:
    query = (
        db.table("positions")
        .select(
            "id,side,entry_avg,quantity,leverage,unrealized_pnl,pnl,is_open,entry_atr,trailing_stop_price,highest_price_seen,exit_reason,session_id,is_sim,created_at,opened_at,closed_at,assets(symbol)"
        )
        .order("created_at", desc=True)
        .limit(limit)
    )

    if is_open is not None:
        query = query.eq("is_open", is_open)
    if session_id_filter:
        query = query.eq("session_id", session_id_filter)

    rows = query.execute().data or []

    symbol_filter_norm = symbol_filter.upper() if symbol_filter else None
    output: List[Dict[str, Any]] = []
    for row in rows:
        symbol = _extract_symbol(row).upper()
        if symbol_filter_norm and symbol != symbol_filter_norm:
            continue

        output.append(
            {
                "id": str(row.get("id")),
                "symbol": symbol,
                "side": str(row.get("side") or "UNKNOWN").upper(),
                "entry_avg": _to_float(row.get("entry_avg")),
                "quantity": _to_float(row.get("quantity")),
                "leverage": _to_int(row.get("leverage"), default=1),
                "unrealized_pnl": _to_float(row.get("unrealized_pnl")),
                "realized_pnl": _to_float(row.get("pnl")),
                "is_open": _to_bool(row.get("is_open"), default=False),
                "entry_atr": _to_float(row.get("entry_atr")),
                "trailing_stop_price": _to_float(row.get("trailing_stop_price"), default=0.0) or None,
                "highest_price_seen": _to_float(row.get("highest_price_seen"), default=0.0) or None,
                "exit_reason": row.get("exit_reason"),
                "session_id": str(row.get("session_id")) if row.get("session_id") else None,
                "is_sim": _to_bool(row.get("is_sim"), default=True),
                "created_at": row.get("created_at"),
                "opened_at": row.get("opened_at"),
                "closed_at": row.get("closed_at"),
            }
        )
    return output


def _compute_orders(
    db: Any,
    status_filter: Optional[str],
    symbol_filter: Optional[str],
    limit: int,
) -> List[Dict[str, Any]]:
    query = db.table("orders").select("id,signal_id,exchange_order_id,price_filled,quantity,fee,status,created_at").order("created_at", desc=True).limit(limit)
    if status_filter:
        query = query.eq("status", status_filter.upper())
    order_rows = query.execute().data or []

    signal_ids = [row.get("signal_id") for row in order_rows if row.get("signal_id")]
    signal_map: Dict[str, Dict[str, Any]] = {}

    if signal_ids:
        signal_rows = (
            db.table("trade_signals")
            .select("id,signal_type,entry_target,assets(symbol)")
            .in_("id", signal_ids)
            .execute()
            .data
            or []
        )
        signal_map = {str(row.get("id")): row for row in signal_rows}

    symbol_filter_norm = symbol_filter.upper() if symbol_filter else None
    output: List[Dict[str, Any]] = []
    for row in order_rows:
        signal_id = str(row.get("signal_id")) if row.get("signal_id") else None
        signal_row = signal_map.get(signal_id or "", {})
        symbol = _extract_symbol(signal_row).upper() if signal_row else "UNKNOWN"
        if symbol_filter_norm and symbol != symbol_filter_norm:
            continue

        filled_price = _to_float(row.get("price_filled"), default=0.0)
        entry_target = _to_float(signal_row.get("entry_target"), default=0.0) if signal_row else 0.0
        slippage_bps: Optional[float] = None
        if entry_target > 0 and filled_price > 0:
            slippage_bps = round(((filled_price - entry_target) / entry_target) * 10000, 2)

        output.append(
            {
                "id": str(row.get("id")),
                "signal_id": signal_id,
                "symbol": symbol,
                "signal_type": str(signal_row.get("signal_type") or "UNKNOWN").upper() if signal_row else "UNKNOWN",
                "exchange_order_id": row.get("exchange_order_id"),
                "price_filled": filled_price,
                "quantity": _to_float(row.get("quantity")),
                "fee": _to_float(row.get("fee")),
                "status": str(row.get("status") or "UNKNOWN").upper(),
                "slippage_bps": slippage_bps,
                "created_at": row.get("created_at"),
            }
        )

    return output


def _compute_events(db: Any, limit: int) -> List[Dict[str, Any]]:
    query = db.table("system_logs").select("id,level,role,message,created_at").order("created_at", desc=True).limit(limit)
    rows = query.execute().data or []
    return [
        {
            "id": str(row.get("id")),
            "level": str(row.get("level") or "INFO").upper(),
            "role": str(row.get("role") or "SYSTEM"),
            "message": str(row.get("message") or ""),
            "created_at": row.get("created_at"),
        }
        for row in rows
    ]


def _normalize_ws_symbol(raw_symbol: str) -> str:
    symbol = raw_symbol.upper().strip()
    if "/" in symbol:
        return symbol
    if symbol.endswith("USDT") and len(symbol) > 4:
        return f"{symbol[:-4]}/USDT"
    return symbol


def _build_kline_from_rows(symbol: str, tf: str, rows: List[Dict[str, Any]]) -> KlineDTO:
    candles: List[KlineCandleDTO] = []
    for row in rows:
        try:
            ts_raw = row.get("time")
            if ts_raw is None and row.get("ts_open"):
                ts_raw = row.get("ts_open")

            if isinstance(ts_raw, str):
                ts_value = int(datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).timestamp())
            elif isinstance(ts_raw, datetime):
                ts_value = int(ts_raw.replace(tzinfo=timezone.utc).timestamp())
            else:
                ts_value = _to_int(ts_raw)

            candle = KlineCandleDTO(
                time=ts_value,
                open=_to_float(row.get("open")),
                high=_to_float(row.get("high")),
                low=_to_float(row.get("low")),
                close=_to_float(row.get("close")),
                volume=_to_float(row.get("volume")),
            )
            candles.append(candle)
        except Exception:
            continue

    if not candles:
        raise APIRequestError(
            code=ErrorCode.E_UPSTREAM_EXCHANGE_502,
            message="no valid candle data available",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    return KlineDTO(symbol=symbol, tf=tf, candles=candles)


def _fetch_cached_klines(db: Any, symbol: str, tf: str, limit: int) -> List[Dict[str, Any]]:
    result = (
        db.table("chart_candle_cache")
        .select("ts_open,open,high,low,close,volume")
        .eq("symbol", symbol)
        .eq("timeframe", tf)
        .order("ts_open", desc=True)
        .limit(limit)
        .execute()
    )
    rows = result.data or []
    rows.reverse()  # oldest -> newest
    return rows


def _load_kline_rows(db: Any, symbol: str, tf: str, limit: int) -> List[Dict[str, Any]]:
    cache_rows: List[Dict[str, Any]] = []
    if db:
        try:
            cache_rows = _fetch_cached_klines(db, symbol=symbol, tf=tf, limit=limit)
        except Exception:
            cache_rows = []

    if cache_rows:
        return cache_rows

    source_rows = _fetch_exchange_klines(symbol=symbol, tf=tf, limit=limit)
    if db:
        try:
            _upsert_kline_cache(db, symbol=symbol, tf=tf, rows=source_rows)
        except Exception:
            pass
    return source_rows


def _get_price_spy() -> PriceSpy:
    global _price_spy
    if _price_spy is None:
        _price_spy = PriceSpy()
    return _price_spy


def _get_strategist() -> Strategist:
    global _strategist
    if _strategist is None:
        _strategist = Strategist()
    return _strategist


def _fetch_exchange_klines(symbol: str, tf: str, limit: int) -> List[Dict[str, Any]]:
    spy = _get_price_spy()
    df = spy.fetch_ohlcv(symbol, tf, limit=limit)
    if df is None or df.empty:
        raise APIRequestError(
            code=ErrorCode.E_UPSTREAM_EXCHANGE_502,
            message="failed to fetch klines from exchange",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details={"symbol": symbol, "tf": tf},
        )

    rows: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        ts = row["timestamp"]
        if isinstance(ts, datetime):
            ts_sec = int(ts.replace(tzinfo=timezone.utc).timestamp())
        else:
            ts_sec = _to_int(ts)

        rows.append(
            {
                "time": ts_sec,
                "open": _to_float(row.get("open")),
                "high": _to_float(row.get("high")),
                "low": _to_float(row.get("low")),
                "close": _to_float(row.get("close")),
                "volume": _to_float(row.get("volume")),
            }
        )
    return rows


def _upsert_kline_cache(db: Any, symbol: str, tf: str, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return

    payload = []
    for row in rows:
        ts_raw = row.get("time")
        if isinstance(ts_raw, int):
            ts_open = datetime.fromtimestamp(ts_raw, tz=timezone.utc).isoformat()
        else:
            ts_open = row.get("ts_open")
            if isinstance(ts_open, datetime):
                ts_open = ts_open.isoformat()
        if not ts_open:
            continue

        payload.append(
            {
                "symbol": symbol,
                "timeframe": tf,
                "ts_open": ts_open,
                "open": _to_float(row.get("open")),
                "high": _to_float(row.get("high")),
                "low": _to_float(row.get("low")),
                "close": _to_float(row.get("close")),
                "volume": _to_float(row.get("volume")),
                "source": "exchange",
            }
        )

    if payload:
        db.table("chart_candle_cache").upsert(payload, on_conflict="symbol,timeframe,ts_open").execute()


def _get_client_limiter(client_ip: str, max_per_minute: int) -> RateLimiter:
    limiter = _client_limiters.get(client_ip)
    if limiter is None or limiter.max_calls != max_per_minute:
        limiter = RateLimiter(max_calls=max_per_minute, period=60.0)
        _client_limiters[client_ip] = limiter
    return limiter


def _build_ws_event(event_type: str, payload: Dict[str, Any], source: str = "api.ws") -> Dict[str, Any]:
    event = WSEvent(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        ts=datetime.now(timezone.utc),
        source=source,
        payload=payload,
    )
    return event.model_dump(mode="json")


def _resolve_ws_payload(topic: str, db: Any, mode: Optional[str]) -> Tuple[str, Dict[str, Any]]:
    if topic == WS_TOPIC_SUMMARY:
        resolved_mode = _resolve_mode(db, mode)
        summary = _compute_summary(db, resolved_mode)
        return topic, {"mode": resolved_mode, "summary": summary.model_dump()}

    if topic == WS_TOPIC_POSITIONS:
        positions = _compute_positions(db, is_open=True, symbol_filter=None, session_id_filter=None, limit=100)
        return topic, {"positions": positions}

    if topic == WS_TOPIC_EVENTS:
        events = _compute_events(db, limit=50)
        return topic, {"events": events}

    match = WS_CHART_TOPIC_PATTERN.match(topic)
    if match:
        symbol, tf = match.groups()
        normalized_symbol = _normalize_ws_symbol(symbol)
        normalized_tf = tf.lower().strip()
        if normalized_tf not in ALLOWED_TFS:
            raise APIRequestError(
                code=ErrorCode.E_VALIDATION_400,
                message="unsupported timeframe",
                status_code=status.HTTP_400_BAD_REQUEST,
                details={"allowed": sorted(ALLOWED_TFS), "tf": normalized_tf},
            )
        rows = _load_kline_rows(db, symbol=normalized_symbol, tf=normalized_tf, limit=DEFAULT_WS_LIMIT)
        dto = _build_kline_from_rows(symbol=normalized_symbol, tf=normalized_tf, rows=rows)
        candles = dto.candles
        last_candle = candles[-1].model_dump() if candles else None
        return topic, {
            "symbol": normalized_symbol,
            "tf": normalized_tf,
            "candles": [candle.model_dump() for candle in candles],
            "kline_last": last_candle,
        }

    raise APIRequestError(
        code=ErrorCode.E_VALIDATION_400,
        message="unsupported ws topic",
        status_code=status.HTTP_400_BAD_REQUEST,
        details={"topic": topic},
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title="Zenith Dashboard API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    cors_origins_raw = os.getenv("API_CORS_ORIGINS", "*").strip()
    cors_origins = ["*"] if cors_origins_raw == "*" else [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id

        read_token = os.getenv("API_READ_TOKEN", "").strip()
        if read_token and request.url.path.startswith("/api/") and request.url.path != "/api/health":
            provided_token = request.headers.get("X-API-Key", "").strip()
            if provided_token != read_token:
                response = _json_error(
                    code=ErrorCode.E_AUTH_401,
                    message="missing or invalid api key",
                    request_id=request_id,
                    http_status=status.HTTP_401_UNAUTHORIZED,
                )
                response.headers["X-Request-Id"] = request_id
                return response

        limit_per_minute = _to_int(os.getenv("API_RATE_LIMIT_PER_MIN", "180"), default=180)
        client_ip = request.client.host if request.client else "unknown"
        limiter = _get_client_limiter(client_ip, max_per_minute=max(1, limit_per_minute))
        if not limiter.allow():
            response = _json_error(
                code=ErrorCode.E_RATE_LIMIT_429,
                message="rate limit exceeded",
                request_id=request_id,
                http_status=status.HTTP_429_TOO_MANY_REQUESTS,
                details={"limit_per_min": limit_per_minute},
            )
            response.headers["X-Request-Id"] = request_id
            return response

        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    @app.exception_handler(APIRequestError)
    async def api_request_error_handler(request: Request, exc: APIRequestError):
        return _json_error(
            code=exc.code,
            message=exc.message,
            request_id=_request_id_from(request),
            http_status=exc.status_code,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return _json_error(
            code=ErrorCode.E_VALIDATION_400,
            message="validation error",
            request_id=_request_id_from(request),
            http_status=status.HTTP_400_BAD_REQUEST,
            details={"errors": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        return _json_error(
            code=ErrorCode.E_INTERNAL_500,
            message="internal server error",
            request_id=_request_id_from(request),
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={"error": str(exc)},
        )

    @app.get("/api/health")
    async def get_health(request: Request):
        db = get_db()
        db_ok = bool(db and _probe_db_health(db))
        data = {
            "status": "ok" if db_ok else "degraded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": {
                "db": db_ok,
            },
        }
        return _json_success(data=data, request_id=_request_id_from(request))

    @app.get("/api/dashboard/summary")
    async def get_dashboard_summary(
        request: Request,
        mode: Optional[str] = Query(default=None, description="PAPER|LIVE"),
    ):
        db = get_db()
        if not db:
            raise APIRequestError(
                code=ErrorCode.E_DB_500,
                message="database is not configured",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        resolved_mode = _resolve_mode(db, mode)
        summary = _compute_summary(db, resolved_mode)
        return _json_success(data=summary.model_dump(), request_id=_request_id_from(request))

    @app.get("/api/performance/review")
    async def get_performance_review(
        request: Request,
        mode: Optional[str] = Query(default=None, description="PAPER|LIVE"),
        days: int = Query(default=7, ge=1, le=365),
        min_trades: int = Query(default=20, ge=1, le=500),
        include_ai: bool = Query(default=True),
    ):
        db = get_db()
        if not db:
            raise APIRequestError(
                code=ErrorCode.E_DB_500,
                message="database is not configured",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        resolved_mode = _resolve_mode(db, mode)
        is_sim = resolved_mode == "PAPER"
        try:
            strategist = _get_strategist()
            payload = strategist.analyze_performance_overview(
                days_range=days,
                is_sim=is_sim,
                min_trades=min_trades,
                include_ai=include_ai,
            )
            payload["mode"] = resolved_mode
            return _json_success(data=payload, request_id=_request_id_from(request))
        except Exception as exc:
            raise APIRequestError(
                code=ErrorCode.E_UPSTREAM_AI_503,
                message="performance review service unavailable",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                details={"reason": str(exc)[:300]},
            )

    @app.get("/api/candidates")
    async def get_candidates(
        request: Request,
        limit: int = Query(default=50, ge=1, le=500),
    ):
        db = get_db()
        if not db:
            raise APIRequestError(
                code=ErrorCode.E_DB_500,
                message="database is not configured",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        candidates = _compute_candidates(db, limit=limit)
        return _json_success(data=[row.model_dump() for row in candidates], request_id=_request_id_from(request))

    @app.get("/api/signals")
    async def get_signals(
        request: Request,
        status_filter: Optional[str] = Query(default=None, alias="status"),
        symbol: Optional[str] = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
    ):
        db = get_db()
        if not db:
            raise APIRequestError(
                code=ErrorCode.E_DB_500,
                message="database is not configured",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        normalized_symbol = symbol.upper() if symbol else None
        signals = _compute_signals(db, status_filter=status_filter, symbol_filter=normalized_symbol, limit=limit)
        return _json_success(data=[row.model_dump() for row in signals], request_id=_request_id_from(request))

    @app.get("/api/positions")
    async def get_positions(
        request: Request,
        is_open: Optional[bool] = Query(default=None),
        symbol: Optional[str] = Query(default=None),
        session_id: Optional[str] = Query(default=None, min_length=3, max_length=64),
        limit: int = Query(default=100, ge=1, le=500),
    ):
        db = get_db()
        if not db:
            raise APIRequestError(
                code=ErrorCode.E_DB_500,
                message="database is not configured",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        normalized_symbol = symbol.upper() if symbol else None
        normalized_session_id = _validate_uuid_or_none(session_id, "session_id")

        rows = _compute_positions(
            db,
            is_open=is_open,
            symbol_filter=normalized_symbol,
            session_id_filter=normalized_session_id,
            limit=limit,
        )
        return _json_success(data=rows, request_id=_request_id_from(request))

    @app.get("/api/orders")
    async def get_orders(
        request: Request,
        status_filter: Optional[str] = Query(default=None, alias="status"),
        symbol: Optional[str] = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
    ):
        db = get_db()
        if not db:
            raise APIRequestError(
                code=ErrorCode.E_DB_500,
                message="database is not configured",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        normalized_symbol = symbol.upper() if symbol else None
        rows = _compute_orders(db, status_filter=status_filter, symbol_filter=normalized_symbol, limit=limit)
        return _json_success(data=rows, request_id=_request_id_from(request))

    @app.get("/api/klines")
    async def get_klines(
        request: Request,
        symbol: str = Query(..., min_length=3, max_length=30),
        tf: str = Query(..., min_length=2, max_length=5),
        limit: int = Query(default=DEFAULT_KLINES_LIMIT, ge=1, le=MAX_KLINES_LIMIT),
    ):
        normalized_symbol = symbol.upper().strip()
        normalized_tf = tf.lower().strip()
        if normalized_tf not in ALLOWED_TFS:
            raise APIRequestError(
                code=ErrorCode.E_VALIDATION_400,
                message="unsupported timeframe",
                status_code=status.HTTP_400_BAD_REQUEST,
                details={"allowed": sorted(ALLOWED_TFS), "tf": normalized_tf},
            )

        db = get_db()
        source_rows = _load_kline_rows(db, symbol=normalized_symbol, tf=normalized_tf, limit=limit)
        kline_dto = _build_kline_from_rows(symbol=normalized_symbol, tf=normalized_tf, rows=source_rows)
        return _json_success(data=kline_dto.model_dump(), request_id=_request_id_from(request))

    @app.get("/api/events")
    async def get_events(
        request: Request,
        limit: int = Query(default=100, ge=1, le=500),
    ):
        db = get_db()
        if not db:
            raise APIRequestError(
                code=ErrorCode.E_DB_500,
                message="database is not configured",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        events = _compute_events(db, limit=limit)
        return _json_success(data=events, request_id=_request_id_from(request))

    @app.get("/api/replay/ai-decisions")
    async def replay_ai_decisions(
        request: Request,
        symbol: Optional[str] = Query(default=None),
        run_id: Optional[str] = Query(default=None, min_length=3, max_length=64),
        tier: Optional[str] = Query(default=None),
        limit: int = Query(default=200, ge=1, le=1000),
    ):
        db = get_db()
        if not db:
            raise APIRequestError(
                code=ErrorCode.E_DB_500,
                message="database is not configured",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        tracker = TelemetryTracker(db=db)
        normalized_run_id = _validate_uuid_or_none(run_id, "run_id")
        rows = tracker.get_ai_decisions(
            symbol=symbol.upper() if symbol else None,
            run_id=normalized_run_id,
            tier=tier,
            limit=limit,
        )
        return _json_success(data=rows, request_id=_request_id_from(request))

    @app.get("/api/replay/rule-evaluations")
    async def replay_rule_evaluations(
        request: Request,
        symbol: Optional[str] = Query(default=None),
        run_id: Optional[str] = Query(default=None, min_length=3, max_length=64),
        rule_name: Optional[str] = Query(default=None),
        limit: int = Query(default=200, ge=1, le=1000),
    ):
        db = get_db()
        if not db:
            raise APIRequestError(
                code=ErrorCode.E_DB_500,
                message="database is not configured",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        tracker = TelemetryTracker(db=db)
        normalized_run_id = _validate_uuid_or_none(run_id, "run_id")
        rows = tracker.get_rule_evaluations(
            symbol=symbol.upper() if symbol else None,
            run_id=normalized_run_id,
            rule_name=rule_name,
            limit=limit,
        )
        return _json_success(data=rows, request_id=_request_id_from(request))

    @app.get("/api/replay/post-trades")
    async def replay_post_trades(
        request: Request,
        run_id: Optional[str] = Query(default=None, min_length=3, max_length=64),
        outcome: Optional[str] = Query(default=None),
        position_id: Optional[str] = Query(default=None, min_length=3, max_length=64),
        limit: int = Query(default=200, ge=1, le=1000),
    ):
        db = get_db()
        if not db:
            raise APIRequestError(
                code=ErrorCode.E_DB_500,
                message="database is not configured",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        tracker = TelemetryTracker(db=db)
        normalized_run_id = _validate_uuid_or_none(run_id, "run_id")
        normalized_position_id = _validate_uuid_or_none(position_id, "position_id")
        rows = tracker.get_post_trade_attribution(
            run_id=normalized_run_id,
            outcome=outcome.upper() if outcome else None,
            position_id=normalized_position_id,
            limit=limit,
        )
        return _json_success(data=rows, request_id=_request_id_from(request))

    @app.get("/api/replay/bundle")
    async def replay_bundle(
        request: Request,
        run_id: str = Query(..., min_length=3, max_length=64),
        limit: int = Query(default=200, ge=1, le=1000),
    ):
        db = get_db()
        if not db:
            raise APIRequestError(
                code=ErrorCode.E_DB_500,
                message="database is not configured",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        tracker = TelemetryTracker(db=db)
        normalized_run_id = _validate_uuid_or_none(run_id, "run_id")
        bundle = tracker.get_replay_bundle(run_id=normalized_run_id or run_id, limit=limit)
        return _json_success(data=bundle, request_id=_request_id_from(request))

    @app.get("/api/ops/hardening/health")
    async def get_hardening_health(request: Request):
        db = get_db()
        if not db:
            raise APIRequestError(
                code=ErrorCode.E_DB_500,
                message="database is not configured",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        service = HardeningService(db=db)
        snapshot = service.get_health_snapshot()
        return _json_success(data=snapshot, request_id=_request_id_from(request))

    @app.get("/api/ops/dual-run/parity")
    async def get_dual_run_parity(
        request: Request,
        primary_mode: str = Query(default="PAPER"),
        secondary_mode: str = Query(default="LIVE"),
        tolerance_pct: float = Query(default=2.0, ge=0.1, le=50.0),
    ):
        db = get_db()
        if not db:
            raise APIRequestError(
                code=ErrorCode.E_DB_500,
                message="database is not configured",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        resolved_primary = _resolve_mode(db, primary_mode)
        resolved_secondary = _resolve_mode(db, secondary_mode)
        primary_summary = _compute_summary(db, resolved_primary).model_dump()
        secondary_summary = _compute_summary(db, resolved_secondary).model_dump()
        parity = compare_dashboard_summary(
            primary=primary_summary,
            secondary=secondary_summary,
            tolerance_pct=tolerance_pct,
        )

        payload = {
            "primary_mode": resolved_primary,
            "secondary_mode": resolved_secondary,
            "primary_summary": primary_summary,
            "secondary_summary": secondary_summary,
            "parity": parity,
        }
        return _json_success(data=payload, request_id=_request_id_from(request))

    @app.get("/api/cutover/status")
    async def get_cutover_status(request: Request):
        db = get_db()
        if not db:
            raise APIRequestError(
                code=ErrorCode.E_DB_500,
                message="database is not configured",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        service = CutoverService(db=db)
        return _json_success(data=service.get_status(), request_id=_request_id_from(request))

    @app.post("/api/cutover/apply")
    async def apply_cutover(
        request: Request,
        primary_dashboard: str = Query(..., min_length=4, max_length=20),
        streamlit_fallback_enabled: bool = Query(default=True),
        actor: str = Query(default="api", min_length=2, max_length=40),
    ):
        db = get_db()
        if not db:
            raise APIRequestError(
                code=ErrorCode.E_DB_500,
                message="database is not configured",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        service = CutoverService(db=db)
        try:
            status_payload = service.apply_cutover(
                primary_dashboard=primary_dashboard,
                fallback_enabled=streamlit_fallback_enabled,
                actor=actor,
            )
        except ValueError as exc:
            raise APIRequestError(
                code=ErrorCode.E_VALIDATION_400,
                message=str(exc),
                status_code=status.HTTP_400_BAD_REQUEST,
                details={"primary_dashboard": primary_dashboard},
            )
        return _json_success(data=status_payload, request_id=_request_id_from(request))

    @app.websocket("/ws")
    async def ws_stream(
        websocket: WebSocket,
        topic: str = Query(..., min_length=3, max_length=120),
        mode: Optional[str] = Query(default=None),
        interval_sec: float = Query(default=2.0, ge=0.5, le=30.0),
        once: bool = Query(default=False),
    ):
        read_token = os.getenv("API_READ_TOKEN", "").strip()
        provided_token = websocket.headers.get("x-api-key", "").strip() or websocket.query_params.get("token", "").strip()
        if read_token and provided_token != read_token:
            await websocket.close(code=1008, reason="unauthorized")
            return

        await websocket.accept()

        try:
            while True:
                db = get_db()
                if not db:
                    await websocket.send_json(
                        _build_ws_event(
                            event_type="system.error",
                            payload={
                                "code": ErrorCode.E_DB_500.value,
                                "message": "database is not configured",
                            },
                            source="api.ws.error",
                        )
                    )
                    await websocket.close(code=1011, reason="db unavailable")
                    return

                try:
                    event_type, payload = _resolve_ws_payload(topic=topic, db=db, mode=mode)
                    await websocket.send_json(_build_ws_event(event_type=event_type, payload=payload))
                except APIRequestError as exc:
                    await websocket.send_json(
                        _build_ws_event(
                            event_type="system.error",
                            payload={
                                "code": exc.code.value,
                                "message": exc.message,
                                "details": exc.details,
                            },
                            source="api.ws.error",
                        )
                    )
                    close_code = 1008 if exc.code == ErrorCode.E_VALIDATION_400 else 1011
                    await websocket.close(code=close_code, reason=exc.message)
                    return

                if once:
                    await websocket.close(code=1000, reason="one-shot")
                    return

                await asyncio.sleep(interval_sec)
        except WebSocketDisconnect:
            return
        except Exception as exc:
            try:
                await websocket.send_json(
                    _build_ws_event(
                        event_type="system.error",
                        payload={
                            "code": ErrorCode.E_INTERNAL_500.value,
                            "message": "websocket internal error",
                            "details": {"error": str(exc)},
                        },
                        source="api.ws.error",
                    )
                )
                await websocket.close(code=1011, reason="internal error")
            except Exception:
                return

    return app


app = create_app()
