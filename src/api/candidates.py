"""
Candidate scan, capability, and symbol typing helpers for dashboard APIs.
"""
from __future__ import annotations

import os
import re
import time
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from src.roles.job_scout import Radar
from src.roles.job_screener import HeadHunter


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


def _clean_cfg_value(raw: Any, default: str = "") -> str:
    if raw is None:
        return default
    return str(raw).replace('"', "").strip()


def _fetch_bot_config_value(db: Any, key: str) -> Optional[Any]:
    result = db.table("bot_config").select("value").eq("key", key).limit(1).execute()
    if result.data:
        return result.data[0].get("value")
    return None


def _env_first(*keys: str) -> str:
    for key in keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return ""


def _parse_symbols_from_env(raw: str, fallback: List[str]) -> List[str]:
    rows = [item.strip().upper() for item in str(raw or "").split(",") if item.strip()]
    if rows:
        return list(dict.fromkeys(rows))
    return fallback


def _connector_from_env(market_type: str) -> Dict[str, Any]:
    prefix = market_type.upper()
    name = _env_first(
        f"{prefix}_API_NAME",
        f"{prefix}_LIVE_API_NAME",
        f"{prefix}_CONNECTOR_NAME",
        f"{prefix}_BROKER_NAME",
    )
    url = _env_first(
        f"{prefix}_API_URL",
        f"{prefix}_LIVE_API_URL",
        f"{prefix}_CONNECTOR_URL",
        f"{prefix}_BROKER_URL",
    )
    key = _env_first(
        f"{prefix}_API_KEY",
        f"{prefix}_LIVE_API_KEY",
        f"{prefix}_CONNECTOR_KEY",
        f"{prefix}_BROKER_API_KEY",
    )

    if url:
        try:
            parsed = urlparse(url)
            host = parsed.netloc or url
            if not name:
                name = f"Custom API ({host})"
        except Exception:
            if not name:
                name = "Custom API"

    configured = bool(name or url or key)
    return {
        "configured": configured,
        "name": name or "Custom API",
        "url": url or None,
        "key_present": bool(key),
    }


def _fetch_yahoo_quotes(symbols: List[str], timeout_sec: float) -> Dict[str, Dict[str, Any]]:
    if not symbols:
        return {}

    url = "https://query1.finance.yahoo.com/v7/finance/quote"
    params = {"symbols": ",".join(symbols)}
    try:
        response = requests.get(url, params=params, timeout=max(2.0, timeout_sec))
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("quoteResponse", {}).get("result", []) or []
    except Exception:
        return {}

    quote_map: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol", "")).upper().strip()
        if not symbol:
            continue
        quote_map[symbol] = {
            "price": _to_float(row.get("regularMarketPrice"), default=0.0),
            "volume": _to_float(row.get("regularMarketVolume"), default=0.0),
            "market_cap": _to_float(row.get("marketCap"), default=0.0),
            "pe_ratio": _to_float(row.get("trailingPE"), default=0.0),
            "change_pct": _to_float(row.get("regularMarketChangePercent"), default=0.0),
            "source": "yahoo_quote",
        }
    return quote_map


def _derive_non_crypto_profile(
    market_type: str,
    volume: float,
    market_cap: float,
    pe_ratio: float,
    change_pct: float,
) -> Tuple[int, str]:
    score = 5
    if volume >= 5_000_000:
        score += 3
    elif volume >= 1_500_000:
        score += 2
    elif volume >= 150_000:
        score += 1

    if market_type == "stock":
        if market_cap >= 30_000_000_000:
            score += 1
        if 0 < pe_ratio <= 40:
            score += 1
    else:
        if abs(change_pct) >= 0.35:
            score += 1

    score = max(5, min(10, int(score)))
    status = "WHITELIST" if score >= 8 else "NEUTRAL"
    return score, status


def scan_non_crypto_candidates(limit_per_type: int = 12, use_quote_api: bool = True) -> List[Dict[str, Any]]:
    default_stocks = [
        "AAPL",
        "MSFT",
        "NVDA",
        "AMZN",
        "GOOGL",
        "META",
        "TSLA",
        "AMD",
        "NFLX",
        "JPM",
        "V",
        "MA",
    ]
    default_gold = ["XAUUSD=X", "GC=F", "MGC=F"]
    default_silver = ["XAGUSD=X", "SI=F"]

    stock_symbols = _parse_symbols_from_env(os.getenv("STOCK_SCAN_SYMBOLS", ""), default_stocks)[:limit_per_type]
    gold_symbols = _parse_symbols_from_env(os.getenv("GOLD_SCAN_SYMBOLS", ""), default_gold)[:limit_per_type]
    silver_symbols = _parse_symbols_from_env(os.getenv("SILVER_SCAN_SYMBOLS", ""), default_silver)[:limit_per_type]
    all_symbols = list(dict.fromkeys(stock_symbols + gold_symbols + silver_symbols))

    quote_map: Dict[str, Dict[str, Any]] = {}
    if use_quote_api:
        timeout_sec = _to_float(os.getenv("YAHOO_QUOTE_TIMEOUT_SEC", "8"), default=8.0)
        quote_map = _fetch_yahoo_quotes(all_symbols, timeout_sec=timeout_sec)

    output: List[Dict[str, Any]] = []

    def _append_rows(symbols: List[str], market_type: str):
        for symbol in symbols:
            quote = quote_map.get(symbol, {})
            price = _to_float(quote.get("price"), default=0.0)
            volume = _to_float(quote.get("volume"), default=10000.0)
            if volume <= 0:
                volume = 10000.0
            market_cap = _to_float(quote.get("market_cap"), default=0.0)
            pe_ratio = _to_float(quote.get("pe_ratio"), default=0.0)
            change_pct = _to_float(quote.get("change_pct"), default=0.0)
            manual_score, fundamental_status = _derive_non_crypto_profile(
                market_type=market_type,
                volume=volume,
                market_cap=market_cap,
                pe_ratio=pe_ratio,
                change_pct=change_pct,
            )
            source_name = quote.get("source", "manual_universe")
            notes = (
                f"paper_non_crypto_scan source={source_name}; "
                f"cap={market_cap:.0f}; pe={pe_ratio:.2f}; change={change_pct:.2f}%"
            )

            output.append(
                {
                    "symbol": symbol,
                    "volume": volume,
                    "candidate_type": market_type,
                    "source": source_name,
                    "price": price,
                    "market_cap": market_cap,
                    "pe_ratio": pe_ratio,
                    "change_pct": change_pct,
                    "manual_score": manual_score,
                    "status": fundamental_status,
                    "notes": notes,
                }
            )

    _append_rows(stock_symbols, "stock")
    _append_rows(gold_symbols, "gold")
    _append_rows(silver_symbols, "silver")
    return output


def _upsert_bot_config_value(db: Any, key: str, value: Any) -> None:
    db.table("bot_config").upsert({"key": key, "value": value}).execute()


def _persist_manual_scan_results(db: Any, qualified_rows: List[Dict[str, Any]], actor: str) -> None:
    if not qualified_rows:
        return

    upsert_rows: List[Dict[str, Any]] = []
    total = max(1, len(qualified_rows))
    for idx, row in enumerate(qualified_rows):
        symbol = str(row.get("symbol", "")).upper()
        if not symbol:
            continue
        manual_score = _to_int(row.get("manual_score"), default=0)
        if manual_score <= 0:
            progress = idx / max(1, total - 1) if total > 1 else 0.0
            manual_score = int(round(10 - (progress * 5)))
            manual_score = max(5, min(10, manual_score))
        status = str(row.get("status") or "NEUTRAL").upper()
        if status not in {"WHITELIST", "BLACKLIST", "NEUTRAL"}:
            status = "NEUTRAL"
        note_text = str(row.get("notes") or "").strip()
        auto_note = (
            f"auto-scan actor={actor}; source={row.get('source', 'manual_scan')}; "
            f"type={row.get('candidate_type', 'other')}; volume={_to_float(row.get('volume'), default=0.0):.2f}"
        )
        upsert_rows.append(
            {
                "symbol": symbol,
                "status": status,
                "manual_score": manual_score,
                "notes": f"{note_text} | {auto_note}" if note_text else auto_note,
            }
        )

    if upsert_rows:
        db.table("fundamental_coins").upsert(upsert_rows).execute()


def run_manual_candidate_scan(
    db: Any,
    spy: Any,
    mode: str,
    limit: int,
    include_non_crypto: bool,
    deep_scan: bool,
    actor: str,
) -> Dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    scan_run_id: Optional[int] = None
    t_total_start = time.perf_counter()

    try:
        db.table("system_logs").insert(
            {
                "role": "Radar",
                "level": "INFO",
                "message": (
                    f"📡 Manual candidate scan requested by {actor} "
                    f"(mode={mode}, include_non_crypto={include_non_crypto}, deep_scan={deep_scan}, limit={limit})"
                ),
            }
        ).execute()
    except Exception:
        pass

    try:
        insert_res = db.table("farming_history").insert({"status": "IN_PROGRESS"}).execute()
        if insert_res.data:
            scan_run_id = _to_int(insert_res.data[0].get("id"), default=0) or None
    except Exception:
        scan_run_id = None

    crypto_candidates: List[Dict[str, Any]] = []
    non_crypto_candidates: List[Dict[str, Any]] = []
    qualified_rows: List[Dict[str, Any]] = []
    error_message: Optional[str] = None
    stage_crypto_sec = 0.0
    stage_non_crypto_sec = 0.0
    stage_screener_sec = 0.0
    stage_persist_sec = 0.0

    try:
        radar = Radar(spy)
        radar_limit = max(20, min(limit, 200))
        if deep_scan:
            radar_limit = max(radar_limit, 120)
        t_stage = time.perf_counter()
        raw_crypto = radar.scan_market(limit=radar_limit)
        stage_crypto_sec = time.perf_counter() - t_stage
        for row in raw_crypto or []:
            symbol = str((row or {}).get("symbol", "")).upper().strip()
            if not symbol:
                continue
            crypto_candidates.append(
                {
                    "symbol": symbol,
                    "volume": _to_float((row or {}).get("volume"), default=0.0),
                    "candidate_type": "crypto",
                    "source": "radar_crypto",
                }
            )

        if include_non_crypto:
            t_stage = time.perf_counter()
            non_crypto_candidates = scan_non_crypto_candidates(limit_per_type=max(6, min(limit // 2, 30)))
            stage_non_crypto_sec = time.perf_counter() - t_stage

        merged_by_symbol: Dict[str, Dict[str, Any]] = {}
        for row in crypto_candidates + non_crypto_candidates:
            symbol = str(row.get("symbol", "")).upper().strip()
            if not symbol:
                continue
            prev = merged_by_symbol.get(symbol)
            if not prev or _to_float(row.get("volume"), default=0.0) > _to_float(prev.get("volume"), default=0.0):
                merged_by_symbol[symbol] = row

        merged_rows = list(merged_by_symbol.values())
        merged_rows.sort(key=lambda item: _to_float(item.get("volume"), default=0.0), reverse=True)

        screener = HeadHunter(db_client=db)
        t_stage = time.perf_counter()
        screened = screener.screen_market(merged_rows) if merged_rows else []
        stage_screener_sec = time.perf_counter() - t_stage

        screened_symbols = set()
        for row in screened or []:
            if isinstance(row, str):
                screened_symbols.add(row.upper())
            elif isinstance(row, dict):
                symbol = str(row.get("symbol", "")).upper().strip()
                if symbol:
                    screened_symbols.add(symbol)

        for row in merged_rows:
            symbol = str(row.get("symbol", "")).upper()
            if symbol in screened_symbols:
                qualified_rows.append(row)
            if len(qualified_rows) >= limit:
                break

        t_stage = time.perf_counter()
        _persist_manual_scan_results(db, qualified_rows=qualified_rows, actor=actor)
        symbols = [str(row.get("symbol", "")).upper() for row in qualified_rows if row.get("symbol")]
        if symbols:
            _upsert_bot_config_value(db, "ACTIVE_CANDIDATES", json.dumps(symbols))
        _upsert_bot_config_value(db, "LAST_FARM_TIME", str(datetime.now(timezone.utc).timestamp()))
        stage_persist_sec = time.perf_counter() - t_stage

    except Exception as exc:
        error_message = str(exc)[:300]

    completed_at = datetime.now(timezone.utc)
    status_text = "FAILED" if error_message else "COMPLETED"
    total_elapsed_sec = time.perf_counter() - t_total_start
    timing_text = (
        f"timing(total={total_elapsed_sec:.2f}s, crypto={stage_crypto_sec:.2f}s, "
        f"non_crypto={stage_non_crypto_sec:.2f}s, screen={stage_screener_sec:.2f}s, persist={stage_persist_sec:.2f}s)"
    )
    summary_message = (
        f"Manual scan {status_text.lower()}: qualified={len(qualified_rows)}, "
        f"crypto={len(crypto_candidates)}, non_crypto={len(non_crypto_candidates)} | {timing_text}"
    )
    if error_message:
        summary_message = f"{summary_message}, reason={error_message}"

    if scan_run_id:
        try:
            db.table("farming_history").update(
                {
                    "status": status_text,
                    "end_time": completed_at.isoformat(),
                    "candidates_found": len(qualified_rows),
                    "logs": summary_message,
                }
            ).eq("id", scan_run_id).execute()
        except Exception:
            pass

    try:
        db.table("system_logs").insert(
            {
                "role": "Radar",
                "level": "ERROR" if error_message else "SUCCESS",
                "message": f"📡 {summary_message}",
            }
        ).execute()
    except Exception:
        pass

    counts_by_type: Dict[str, int] = {"crypto": 0, "stock": 0, "gold": 0, "silver": 0, "other": 0}
    for row in qualified_rows:
        market_type = normalize_candidate_type(row.get("candidate_type"))
        if market_type not in counts_by_type:
            market_type = "other"
        counts_by_type[market_type] += 1

    payload = {
        "scan_run_id": scan_run_id,
        "status": status_text,
        "mode": mode,
        "actor": actor,
        "started_at": started_at.isoformat(),
        "finished_at": completed_at.isoformat(),
        "scanned_total": len(crypto_candidates) + len(non_crypto_candidates),
        "qualified_total": len(qualified_rows),
        "qualified_symbols": [row.get("symbol") for row in qualified_rows],
        "counts_by_type": counts_by_type,
        "sources": {
            "crypto_radar": len(crypto_candidates),
            "non_crypto_api": len(non_crypto_candidates),
        },
        "include_non_crypto": include_non_crypto,
        "deep_scan": deep_scan,
        "message": summary_message,
        "timing": {
            "total_sec": round(total_elapsed_sec, 3),
            "crypto_sec": round(stage_crypto_sec, 3),
            "non_crypto_sec": round(stage_non_crypto_sec, 3),
            "screen_sec": round(stage_screener_sec, 3),
            "persist_sec": round(stage_persist_sec, 3),
        },
    }
    if error_message:
        payload["error"] = error_message
    return payload


def normalize_candidate_type(raw_value: Any) -> str:
    value = str(raw_value or "").strip().lower()
    aliases = {
        "crypto": "crypto",
        "spot": "crypto",
        "coin": "crypto",
        "coins": "crypto",
        "stock": "stock",
        "stocks": "stock",
        "equity": "stock",
        "equities": "stock",
        "gold": "gold",
        "xau": "gold",
        "silver": "silver",
        "xag": "silver",
    }
    return aliases.get(value, "other")


def infer_candidate_type(symbol: str, market_type: Optional[str]) -> str:
    normalized_market_type = normalize_candidate_type(market_type)
    if normalized_market_type != "other":
        return normalized_market_type

    symbol_upper = str(symbol or "").upper()
    if "XAU" in symbol_upper or "GOLD" in symbol_upper:
        return "gold"
    if "XAG" in symbol_upper or "SILVER" in symbol_upper:
        return "silver"
    if symbol_upper in {"GC=F", "MGC=F"}:
        return "gold"
    if symbol_upper in {"SI=F", "SIL=F"}:
        return "silver"
    if symbol_upper.endswith("=X"):
        if "XAU" in symbol_upper:
            return "gold"
        if "XAG" in symbol_upper:
            return "silver"

    if "/" in symbol_upper:
        base, quote = symbol_upper.split("/", 1)
        if quote in {"USDT", "BTC", "ETH", "THB", "BUSD"}:
            return "crypto"
        if quote in {"USD", "EUR", "JPY", "GBP"} and len(base) <= 6 and base.isalpha():
            return "stock"

    if len(symbol_upper) <= 6 and symbol_upper.replace("-", "").isalpha():
        return "stock"

    return "other"


def extract_first_integer(raw_text: Any) -> Optional[int]:
    if raw_text is None:
        return None
    match = re.search(r"(\d+)", str(raw_text))
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def build_candidate_capability_matrix() -> List[Dict[str, Any]]:
    has_binance_keys = bool(os.getenv("BINANCE_API_KEY", "").strip() and os.getenv("BINANCE_SECRET", "").strip())
    stock_connector = _connector_from_env("stock")
    gold_connector = _connector_from_env("gold")
    silver_connector = _connector_from_env("silver")

    def _row_from_connector(market_type: str, connector: Dict[str, Any], fallback_detail: str) -> Dict[str, Any]:
        connector_enabled = bool(connector.get("configured"))
        if connector_enabled:
            return {
                "market_type": market_type,
                "paper_enabled": True,
                "live_enabled": True,
                "api_name": connector.get("name") or "Custom API",
                "connected": True,
                "ready": True,
                "detail": f"Live tradable via configured connector ({connector.get('name')}).",
            }

        return {
            "market_type": market_type,
            "paper_enabled": True,
            "live_enabled": False,
            "api_name": "Yahoo Finance (scan only)",
            "connected": True,
            "ready": False,
            "detail": fallback_detail,
        }

    scan_exchange = os.getenv("RADAR_SCAN_EXCHANGE_ID", "bybit").strip() or "bybit"

    return [
        {
            "market_type": "crypto",
            "paper_enabled": True,
            "live_enabled": has_binance_keys,
            "api_name": "Binance TH (live) + Global Radar scan",
            "connected": has_binance_keys,
            "ready": has_binance_keys,
            "detail": (
                f"Live trading uses Binance TH keys. Candidate scan uses global public exchange ({scan_exchange})"
                " to expand radar coverage."
            ),
        },
        _row_from_connector(
            market_type="stock",
            connector=stock_connector,
            fallback_detail="Stock scan works via Yahoo quote fallback. Configure STOCK_API_URL (or STOCK_API_NAME) for LIVE support.",
        ),
        _row_from_connector(
            market_type="gold",
            connector=gold_connector,
            fallback_detail="Gold scan works via Yahoo quote fallback. Configure GOLD_API_URL (or GOLD_API_NAME) for LIVE support.",
        ),
        _row_from_connector(
            market_type="silver",
            connector=silver_connector,
            fallback_detail="Silver scan works via Yahoo quote fallback. Configure SILVER_API_URL (or SILVER_API_NAME) for LIVE support.",
        ),
    ]


def build_candidate_agent_map(db: Any) -> List[Dict[str, Any]]:
    ai_model = _clean_cfg_value(_fetch_bot_config_value(db, "AI_MODEL"), default="")
    minimax_model = os.getenv("MINIMAX_CODING_MODEL", "MiniMax-M2.5").strip()
    strategist_model = ai_model or f"MINIMAX_CODING:{minimax_model} (Gemini fallback)"

    return [
        {
            "agent_id": "radar",
            "name": "Radar",
            "agent_type": "NON_AI",
            "model_or_engine": "Deterministic scanner",
            "functions": ["scan_market", "PriceSpy.get_top_symbols"],
            "libraries": ["ccxt", "pandas"],
            "help_text": "Scans broad market universe and returns high-interest symbols for candidate stage.",
            "candidate_scope": True,
        },
        {
            "agent_id": "headhunter",
            "name": "HeadHunter",
            "agent_type": "NON_AI",
            "model_or_engine": "Rule-based screener",
            "functions": ["screen_market", "load_config"],
            "libraries": ["Supabase client"],
            "help_text": "Filters candidates by liquidity, whitelist/blacklist status, and trading universe rules.",
            "candidate_scope": True,
        },
        {
            "agent_id": "strategist",
            "name": "Strategist",
            "agent_type": "AI",
            "model_or_engine": strategist_model,
            "functions": ["analyze_market", "analyze_performance_overview"],
            "libraries": ["MiniMax API", "google-genai"],
            "help_text": "Performs deep market reasoning and narrative analysis for trade direction.",
            "candidate_scope": False,
        },
        {
            "agent_id": "judge",
            "name": "Judge",
            "agent_type": "RULE_ENGINE",
            "model_or_engine": "Deterministic risk guardrails",
            "functions": ["evaluate"],
            "libraries": ["Built-in rule engine"],
            "help_text": "Applies risk, position sizing, and validation checks before execution.",
            "candidate_scope": False,
        },
        {
            "agent_id": "sniper",
            "name": "SniperExecutor",
            "agent_type": "EXECUTION",
            "model_or_engine": "Execution engine",
            "functions": ["execute_order"],
            "libraries": ["ccxt"],
            "help_text": "Submits approved orders and records fills, positions, and execution results.",
            "candidate_scope": False,
        },
        {
            "agent_id": "pricespy",
            "name": "PriceSpy",
            "agent_type": "NON_AI",
            "model_or_engine": "Market data collector",
            "functions": ["fetch_ohlcv", "calculate_indicators", "get_top_symbols"],
            "libraries": ["ccxt", "pandas", "pandas_ta"],
            "help_text": "Collects market data and computes indicators used by scanner, analyst, and execution roles.",
            "candidate_scope": True,
        },
        {
            "agent_id": "walletsync",
            "name": "WalletSync",
            "agent_type": "SERVICE",
            "model_or_engine": "Periodic sync service",
            "functions": ["sync_wallet"],
            "libraries": ["ccxt", "requests", "Supabase client"],
            "help_text": "Syncs wallet balances and logs system health. Service component, not part of core 6-role line.",
            "candidate_scope": False,
        },
    ]


def compute_candidate_insights(db: Any, mode: str, limit: int, log_limit: int) -> Dict[str, Any]:
    trading_universe = _clean_cfg_value(_fetch_bot_config_value(db, "TRADING_UNIVERSE"), default="ALL").upper()
    if trading_universe not in {"ALL", "SAFE_LIST", "TOP_30", "TOP_100"}:
        trading_universe = "ALL"

    source_counts = {
        "fundamental_coins_total": 0,
        "assets_active_total": 0,
    }

    try:
        fundamental_count = db.table("fundamental_coins").select("symbol", count="exact").limit(1).execute()
        source_counts["fundamental_coins_total"] = _to_int(getattr(fundamental_count, "count", 0), default=0)
    except Exception:
        source_counts["fundamental_coins_total"] = 0

    try:
        assets_count = db.table("assets").select("id", count="exact").eq("status", "active").limit(1).execute()
        source_counts["assets_active_total"] = _to_int(getattr(assets_count, "count", 0), default=0)
    except Exception:
        source_counts["assets_active_total"] = 0

    primary_source = "fundamental_coins"
    candidate_rows: List[Dict[str, Any]] = []

    try:
        result = (
            db.table("fundamental_coins")
            .select("symbol,status,manual_score,notes,updated_at")
            .order("manual_score", desc=True)
            .limit(limit)
            .execute()
        )
        candidate_rows = result.data or []
    except Exception:
        candidate_rows = []

    if not candidate_rows:
        primary_source = "assets"
        try:
            fallback = (
                db.table("assets")
                .select("symbol,status,market_type,tags,updated_at")
                .eq("status", "active")
                .limit(limit)
                .execute()
            )
            candidate_rows = fallback.data or []
        except Exception:
            candidate_rows = []

    # PAPER mode should always preview multi-asset capability even without live broker connectors.
    if mode == "PAPER":
        try:
            preview_rows = scan_non_crypto_candidates(limit_per_type=10, use_quote_api=False)
        except Exception:
            preview_rows = []
        existing_symbols = {
            str(row.get("symbol", "")).upper().strip()
            for row in candidate_rows
            if row.get("symbol")
        }
        appended_count = 0
        for row in preview_rows:
            symbol = str(row.get("symbol", "")).upper().strip()
            if not symbol or symbol in existing_symbols:
                continue
            existing_symbols.add(symbol)
            candidate_rows.append(
                {
                    "symbol": symbol,
                    "status": str(row.get("status") or "NEUTRAL").upper(),
                    "manual_score": _to_int(row.get("manual_score"), default=6),
                    "notes": str(row.get("notes") or "paper capability preview"),
                    "market_type": row.get("candidate_type"),
                    "updated_at": None,
                }
            )
            appended_count += 1
            if len(candidate_rows) >= limit:
                break
        if appended_count > 0:
            primary_source = f"{primary_source}+paper_preview"

    symbol_list = [str(row.get("symbol", "")).upper() for row in candidate_rows if row.get("symbol")]
    asset_map: Dict[str, Dict[str, Any]] = {}
    if symbol_list:
        try:
            asset_rows = (
                db.table("assets")
                .select("symbol,market_type,status,tags")
                .in_("symbol", symbol_list)
                .execute()
                .data
                or []
            )
            asset_map = {
                str(row.get("symbol", "")).upper(): row
                for row in asset_rows
                if row.get("symbol")
            }
        except Exception:
            asset_map = {}

    capability_rows = build_candidate_capability_matrix()
    live_support_map = {str(row["market_type"]): bool(row["live_enabled"]) for row in capability_rows}

    candidates_raw: List[Dict[str, Any]] = []
    for idx, row in enumerate(candidate_rows, start=1):
        symbol = str(row.get("symbol", "UNKNOWN")).upper()
        status_val = str(row.get("status", "NEUTRAL")).upper()
        manual_score = _to_float(row.get("manual_score"), default=5.0)
        liquidity_score = max(0.0, min(100.0, manual_score * 10.0))
        whitelist_pass = status_val == "WHITELIST"
        tradable = status_val != "BLACKLIST"
        reject_reason = None if tradable else "BLACKLISTED_BY_FUNDAMENTAL"
        if trading_universe == "SAFE_LIST" and not whitelist_pass:
            tradable = False
            reject_reason = "NOT_IN_WHITELIST"

        asset_meta = asset_map.get(symbol, {})
        candidate_type = infer_candidate_type(
            symbol=symbol,
            market_type=asset_meta.get("market_type") or row.get("market_type"),
        )
        live_ready = bool(live_support_map.get(candidate_type, False))
        live_tradable = tradable and live_ready

        scanner_reason_parts = [
            f"source={primary_source}",
            f"status={status_val}",
            f"universe={trading_universe}",
            f"whitelist_pass={str(whitelist_pass).lower()}",
            f"manual_score={manual_score:.1f}",
            f"type={candidate_type}",
        ]
        note_text = str(row.get("notes", "")).strip()
        if note_text:
            scanner_reason_parts.append(f"note={note_text}")
        if reject_reason:
            scanner_reason_parts.append(f"reject={reject_reason}")

        candidates_raw.append(
            {
                "symbol": symbol,
                "screener_rank": idx,
                "liquidity_score": round(liquidity_score, 2),
                "tradable": tradable,
                "reject_reason": reject_reason,
                "candidate_type": candidate_type,
                "source": primary_source,
                "fundamental_status": status_val,
                "whitelist_state": status_val,
                "whitelist_pass": whitelist_pass,
                "universe_mode": trading_universe,
                "manual_score": round(manual_score, 2),
                "scanner_reason": " | ".join(scanner_reason_parts),
                "live_tradable": live_tradable,
                "live_block_reason": None if live_tradable else (reject_reason or "LIVE_CONNECTOR_NOT_READY"),
            }
        )

    if mode == "LIVE":
        visible_candidates = [row for row in candidates_raw if row["live_tradable"]]
    else:
        visible_candidates = candidates_raw

    latest_scan: Optional[Dict[str, Any]] = None
    try:
        scan_rows = (
            db.table("farming_history")
            .select("id,start_time,end_time,status,candidates_found,logs,created_at")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        if scan_rows:
            row = scan_rows[0]
            passed_count = _to_int(row.get("candidates_found"), default=0)
            inferred_universe = extract_first_integer(row.get("logs"))
            if inferred_universe is None or inferred_universe < passed_count:
                inferred_universe = passed_count
            latest_scan = {
                "scan_run_id": str(row.get("id")),
                "start_time": row.get("start_time"),
                "end_time": row.get("end_time"),
                "status": str(row.get("status") or "UNKNOWN").upper(),
                "universe_size": inferred_universe,
                "passed_count": passed_count,
                "reject_count": max(0, inferred_universe - passed_count),
                "logs": str(row.get("logs") or ""),
                "created_at": row.get("created_at"),
            }
    except Exception:
        latest_scan = None

    scanner_logs: List[Dict[str, Any]] = []
    try:
        logs_rows = (
            db.table("system_logs")
            .select("id,level,role,message,created_at")
            .order("created_at", desc=True)
            .limit(max(log_limit * 3, 15))
            .execute()
            .data
            or []
        )
        scan_keywords = {"farm", "scan", "radar", "hunter", "candidate", "harvest"}
        scan_roles = {"SPY", "SYSTEM", "HEADHUNTER", "RADAR"}
        for row in logs_rows:
            role = str(row.get("role") or "SYSTEM")
            message = str(row.get("message") or "")
            role_ok = role.upper() in scan_roles
            message_ok = any(keyword in message.lower() for keyword in scan_keywords)
            if not (role_ok and message_ok):
                continue
            scanner_logs.append(
                {
                    "id": str(row.get("id")),
                    "level": str(row.get("level") or "INFO").upper(),
                    "role": role,
                    "message": message,
                    "created_at": row.get("created_at"),
                }
            )
            if len(scanner_logs) >= log_limit:
                break
    except Exception:
        scanner_logs = []

    type_descriptions = {
        "crypto": "Digital assets and crypto pairs.",
        "stock": "Equity symbols from stock universe.",
        "gold": "Gold and gold-linked symbols.",
        "silver": "Silver and silver-linked symbols.",
        "other": "Symbols not mapped to a standard market type.",
    }
    type_order = ["crypto", "stock", "gold", "silver", "other"]
    candidate_types: List[Dict[str, Any]] = []
    for market_type in type_order:
        total = len([row for row in visible_candidates if row["candidate_type"] == market_type])
        live_tradable = len(
            [row for row in visible_candidates if row["candidate_type"] == market_type and row["live_tradable"]]
        )
        if market_type == "other" and total == 0:
            continue
        candidate_types.append(
            {
                "market_type": market_type,
                "total": total,
                "live_tradable": live_tradable,
                "description": type_descriptions.get(market_type, ""),
            }
        )

    if source_counts["fundamental_coins_total"] <= 3:
        if mode == "PAPER":
            why_limited_note = (
                "Base fundamental table is small, so PAPER mode auto-includes stock/gold/silver preview symbols."
            )
        else:
            why_limited_note = (
                "Candidate list currently follows fundamental_coins table. Update this table or scanner feed to expand coverage."
            )
    else:
        why_limited_note = None

    return {
        "mode": mode,
        "trading_universe": trading_universe,
        "primary_source": primary_source,
        "source_counts": source_counts,
        "total_candidates_raw": len(candidates_raw),
        "total_candidates_visible": len(visible_candidates),
        "why_limited_note": why_limited_note,
        "latest_scan": latest_scan,
        "candidate_types": candidate_types,
        "capabilities": capability_rows,
        "agents": build_candidate_agent_map(db),
        "scanner_logs": scanner_logs,
        "candidates": visible_candidates,
    }
