from __future__ import annotations

from typing import Any, Dict, List, Optional


class HeadHunter:
    """
    THE HEAD HUNTER (Screener)
    Role: Filters assets by fundamentals, liquidity, whitelist policy, and universe mode.
    """

    ALLOWED_UNIVERSE = {"ALL", "SAFE_LIST", "TOP_30", "TOP_100"}
    ALLOWED_WHITELIST_POLICY = {"STRICT", "RELAXED", "IGNORE"}

    def __init__(self, db_client=None):
        self.db = db_client
        self.min_volume = 10000.0
        self.universe = "TOP_100"
        self.whitelist_policy = "RELAXED"

    def _normalize_status(self, raw_status: Any) -> str:
        normalized = str(raw_status or "NEUTRAL").strip().upper()
        if normalized not in {"WHITELIST", "BLACKLIST", "NEUTRAL"}:
            return "NEUTRAL"
        return normalized

    def _normalize_universe(self, raw_value: Any) -> str:
        normalized = str(raw_value or "TOP_100").replace('"', "").strip().upper()
        if normalized in self.ALLOWED_UNIVERSE:
            return normalized
        return "TOP_100"

    def _normalize_whitelist_policy(self, raw_value: Any) -> str:
        normalized = str(raw_value or "RELAXED").replace('"', "").strip().upper()
        if normalized in self.ALLOWED_WHITELIST_POLICY:
            return normalized
        return "RELAXED"

    def load_config(self):
        """Reload screening constraints from DB."""
        if not self.db:
            return
        try:
            cfg = self.db.table("bot_config").select("*").execute()
            cfg_dict = {str(row.get("key")): row.get("value") for row in (cfg.data or [])}
            self.min_volume = float(cfg_dict.get("MIN_VOLUME", 10000))
            self.universe = self._normalize_universe(cfg_dict.get("TRADING_UNIVERSE", "TOP_100"))
            self.whitelist_policy = self._normalize_whitelist_policy(cfg_dict.get("WHITELIST_POLICY", "RELAXED"))
        except Exception as e:
            print(f"HeadHunter Config Error: {e}")

    def _fetch_fundamental_status(self) -> Dict[str, str]:
        f_data: Dict[str, str] = {}
        if not self.db:
            return f_data
        try:
            print("   [HeadHunter] Fetching fundamental_coins table...")
            rows = self.db.table("fundamental_coins").select("*").execute()
            print(f"   [HeadHunter] Fetched {len(rows.data)} rows.")
            for row in rows.data or []:
                symbol = str(row.get("symbol", "")).upper().strip()
                if not symbol:
                    continue
                f_data[symbol] = self._normalize_status(row.get("status"))
        except Exception as e:
            print(f"   [HeadHunter] DB Error: {e}")
        return f_data

    def _parse_candidate(self, coin: Any) -> Optional[Dict[str, Any]]:
        if isinstance(coin, str):
            symbol = coin.strip().upper()
            if not symbol:
                return None
            return {"symbol": symbol, "volume": 0.0}
        if isinstance(coin, dict):
            symbol = str(coin.get("symbol", "")).upper().strip()
            if not symbol:
                return None
            parsed = dict(coin)
            try:
                parsed["volume"] = float(parsed.get("volume", 0) or 0)
            except Exception:
                parsed["volume"] = 0.0
            parsed["symbol"] = symbol
            return parsed
        return None

    def _volume_threshold_for(self, status: str) -> float:
        if status == "WHITELIST" and self.whitelist_policy == "RELAXED":
            return max(0.0, self.min_volume * 0.5)
        return self.min_volume

    def _passes_universe(self, status: str) -> bool:
        if status == "BLACKLIST":
            return False
        if self.universe == "SAFE_LIST":
            return status == "WHITELIST"
        if self.whitelist_policy == "STRICT":
            return status == "WHITELIST"
        return True

    def _apply_universe_limit(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if self.universe == "TOP_30":
            return rows[:30]
        if self.universe == "TOP_100":
            return rows[:100]
        return rows

    def screen_market(self, candidates):
        """
        Filters candidates by blacklist/whitelist policy, liquidity threshold, and universe mode.
        """
        self.load_config()
        f_data = self._fetch_fundamental_status()

        qualified: List[Dict[str, Any]] = []
        rejected_log_count = 0
        rejected_reason = {"blacklist": 0, "volume": 0, "whitelist": 0}

        print(f"🕵️ Head Hunter: Screening {len(candidates)} candidates...")
        print(
            f"   (Mode: {self.universe}, Min Vol: ${self.min_volume:,.0f}, "
            f"Whitelist Policy: {self.whitelist_policy})"
        )

        for coin in candidates:
            parsed = self._parse_candidate(coin)
            if not parsed:
                continue
            symbol = parsed["symbol"]
            vol = float(parsed.get("volume", 0) or 0)
            status = f_data.get(symbol, "NEUTRAL")
            status = self._normalize_status(status)

            if status == "BLACKLIST":
                rejected_reason["blacklist"] += 1
                if rejected_log_count < 5:
                    print(f"HeadHunter: Rejected {symbol} (BLACKLIST)")
                    rejected_log_count += 1
                continue

            vol_threshold = self._volume_threshold_for(status)
            if vol < vol_threshold:
                rejected_reason["volume"] += 1
                if rejected_log_count < 5:
                    print(f"HeadHunter: Rejected {symbol} (Vol ${vol:,.0f} < ${vol_threshold:,.0f})")
                    rejected_log_count += 1
                continue

            if not self._passes_universe(status):
                rejected_reason["whitelist"] += 1
                if rejected_log_count < 5:
                    print(f"HeadHunter: Rejected {symbol} (Universe/Whitelist rule)")
                    rejected_log_count += 1
                continue

            parsed["status"] = status
            parsed["whitelist_pass"] = status == "WHITELIST"
            parsed["volume_threshold"] = vol_threshold
            qualified.append(parsed)

        qualified.sort(key=lambda c: float(c.get("volume", 0) or 0), reverse=True)
        qualified = self._apply_universe_limit(qualified)

        for idx, row in enumerate(qualified, start=1):
            row["screener_rank"] = idx

        print(
            f"✅ Head Hunter: Passed {len(qualified)}/{len(candidates)} candidates "
            f"(rejects: {rejected_reason})."
        )
        return qualified
