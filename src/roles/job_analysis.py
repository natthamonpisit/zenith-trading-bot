from google import genai
import os
import json
import requests
from datetime import datetime, timedelta, timezone
from tenacity import retry, stop_after_attempt, wait_fixed
from pydantic import BaseModel, Field
from src.database import get_db

# Error handling utilities
from src.utils import CircuitBreaker, ExternalAPIError


class _GeminiModelRef:
    """Compatibility shim to keep model_name access pattern intact."""

    def __init__(self, model_name: str):
        self.model_name = model_name

# --- THE STRATEGIST (AI) ---
class Strategist:
    """
    THE STRATEGIST (AI Reasoning Engine)
    Uses provider routing for decision analysis:
    - MiniMax Coding Plan (primary for complex decision payloads)
    - Gemini (fallback and report generation)
    """
    def __init__(self):
        # Initialize database first (needed for saving model info)
        self.db = get_db()

        # MiniMax Coding Plan configuration (primary for complex decision analysis)
        self.minimax_coding_key = os.environ.get("MINIMAX_CODING_PLAN_KEY", "").strip()
        self.minimax_model = os.environ.get("MINIMAX_CODING_MODEL", "MiniMax-M2.5").strip()
        self.minimax_base_url = os.environ.get("MINIMAX_API_BASE_URL", "https://api.minimax.io/v1").strip().rstrip("/")
        try:
            self.minimax_timeout_sec = int(float(os.environ.get("MINIMAX_TIMEOUT_SEC", "20")))
        except (TypeError, ValueError):
            self.minimax_timeout_sec = 20
        try:
            self.minimax_complexity_threshold = int(float(os.environ.get("MINIMAX_COMPLEXITY_THRESHOLD", "10")))
        except (TypeError, ValueError):
            self.minimax_complexity_threshold = 10

        prefer_provider = os.environ.get("STRATEGIST_PRIMARY_PROVIDER", "MINIMAX_CODING").strip().upper()
        self.prefer_minimax_for_decision = prefer_provider in {"MINIMAX_CODING", "MINIMAX", "CODING_PLAN"}
        self.last_model_used = "UNSET"

        if self.minimax_coding_key:
            print(f"🧠 MiniMax Coding enabled for decision analysis ({self.minimax_model})")
        else:
            print("ℹ️ MINIMAX_CODING_PLAN_KEY not found; strategist decisions will use Gemini.")

        # Ensure Gemini API key is loaded and initialize new SDK client.
        self.gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not self.gemini_key:
            print("⚠️ GEMINI_API_KEY not found in environment")

        self.gemini_client = None
        if self.gemini_key:
            try:
                self.gemini_client = genai.Client(api_key=self.gemini_key)
            except Exception as e:
                print(f"⚠️ Failed to initialize google.genai client: {e}")

        # Dynamic Gemini model selection (used as fallback + report generation)
        self.gemini_model_name = self._select_best_model()
        # Keep .model.model_name compatibility for existing telemetry paths.
        self.model = _GeminiModelRef(self.gemini_model_name)

        # Circuit breakers for provider protection
        self.gemini_breaker = CircuitBreaker(
            name="GEMINI_AI",
            failure_threshold=3,  # Stricter for AI
            timeout=90.0  # Longer recovery for AI
        )
        self.minimax_breaker = CircuitBreaker(
            name="MINIMAX_CODING_AI",
            failure_threshold=3,
            timeout=90.0
        )
    
    def _select_best_model(self):
        """
        Dynamically select the best available Gemini model.
        Tries models in order of preference with automatic fallback.
        """
        # Model preference order (newest/best first)
        preferred_models = [
            'gemini-2.0-flash-exp',      # Latest experimental (if available)
            'gemini-2.0-flash',           # Latest stable 2.0
            'gemini-1.5-flash-latest',    # Latest 1.5 Flash
            'gemini-1.5-flash',           # Stable 1.5 Flash
            'gemini-1.5-pro',             # Fallback to Pro
            'gemini-pro',                 # Legacy fallback
        ]

        selected_model_name = None

        if not self.gemini_client:
            selected_model_name = 'gemini-2.0-flash'
            print(f"⚠️ Gemini client unavailable. Using fallback model name: {selected_model_name}")
            return selected_model_name

        try:
            # List all available models
            available_models = list(self.gemini_client.models.list())
            available_names = [str(m.name).split('/')[-1] for m in available_models if getattr(m, "name", None)]

            print(f"🔍 Available Gemini models: {', '.join(available_names[:5])}...")

            # Try each preferred model in order
            for model_name in preferred_models:
                if model_name in available_names:
                    selected_model_name = model_name
                    print(f"✅ Selected Gemini model: {model_name}")
                    break

            # If no preferred model works, use first available
            if not selected_model_name and available_names:
                selected_model_name = available_names[0]
                print(f"⚠️ Using fallback model: {selected_model_name}")

        except Exception as e:
            print(f"❌ Failed to list models: {e}")

        # Ultimate fallback (most stable)
        if not selected_model_name:
            selected_model_name = 'gemini-2.0-flash'
            print(f"⚠️ Using hardcoded fallback: {selected_model_name}")

        # Save to database
        try:
            self.db.table("bot_config").upsert({
                "key": "AI_MODEL",
                "value": selected_model_name
            }).execute()
        except Exception:
            pass

        return selected_model_name

    def _mark_active_model(self, model_name: str):
        self.last_model_used = model_name
        if not self.db:
            return
        try:
            self.db.table("bot_config").upsert({
                "key": "AI_MODEL",
                "value": model_name
            }).execute()
        except Exception as e:
            print(f"⚠️ Failed to update active AI model: {e}")

    def _payload_complexity_score(self, payload):
        if isinstance(payload, dict):
            score = len(payload)
            for value in payload.values():
                if isinstance(value, (dict, list)):
                    score += len(value)
                else:
                    score += 1
            return score
        if isinstance(payload, list):
            return len(payload)
        return 1

    def _should_use_minimax_for_decision(self, tech_data, intent: str) -> bool:
        if not self.minimax_coding_key:
            return False
        if not self.prefer_minimax_for_decision:
            return False

        # ENTRY/EXIT decisions are the high-importance lane.
        if intent in {"ENTRY", "EXIT"}:
            complexity = self._payload_complexity_score(tech_data or {})
            return complexity >= self.minimax_complexity_threshold

        return False

    def _normalize_ai_result(self, result, intent: str):
        data = result if isinstance(result, dict) else {}
        safe_action = "HOLD" if intent == "EXIT" else "WAIT"
        allowed = {"EXIT": {"SELL", "HOLD"}, "ENTRY": {"BUY", "WAIT"}}
        recommendation = str(data.get("recommendation", safe_action)).upper()
        if recommendation not in allowed.get(intent, {"WAIT"}):
            recommendation = safe_action

        try:
            confidence = float(data.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0

        try:
            sentiment = float(data.get("sentiment_score", 0))
        except (TypeError, ValueError):
            sentiment = 0.0

        return {
            "sentiment_score": max(-1.0, min(1.0, sentiment)),
            "confidence": max(0.0, min(100.0, confidence)),
            "reasoning": str(data.get("reasoning", "")),
            "recommendation": recommendation,
        }

    def analyze_market(self, snapshot_id, asset_symbol, tech_data, intent="ENTRY"):
        """
        Sends market data to Gemini and expects a strict JSON response.
        :param intent: "ENTRY" (look for BUY) or "EXIT" (look for SELL)
        """
        
        # Customize task based on intent
        if intent == "EXIT":
            task_instruction = "Current Status: HOLDING POSITION. Evaluate for SELL (Exit) or HOLD. DO NOT recommend BUY."
            valid_actions = '"SELL" | "HOLD"'
        else: # ENTRY
            task_instruction = "Current Status: NO POSITION. Evaluate for BUY (Entry) only. DO NOT recommend SELL."
            valid_actions = '"BUY" | "WAIT"'

        # Build trend context string for AI
        trend_context = ""
        if 'market_trend' in tech_data:
            trend = tech_data['market_trend']
            trend_context = f"""

**MARKET TREND ANALYSIS:**
- Overall Trend: {trend.get('trend', 'UNKNOWN')}
- Trend Strength: {trend.get('strength', 0):.0f}%
- Confidence: {trend.get('confidence', 0):.0f}%
- EMA Alignment: {trend.get('signals', {}).get('ema_aligned', 'UNKNOWN')}
- ADX: {trend.get('signals', {}).get('adx', 0):.1f}
- Price vs EMA200: {trend.get('signals', {}).get('price_vs_ema200', 'UNKNOWN')}

**CONTEXT:** In downtrends, be MORE CONSERVATIVE. Require stronger bullish signals.
Consider: Is this asset showing RELATIVE STRENGTH vs overall market?
"""

        prompt = f"""
        You are a Senior Crypto Trader & Risk Analyst (The Strategist).
        Analyze: {asset_symbol}

        {task_instruction}

        Technical Data:
        {json.dumps(tech_data, default=str)}

        {trend_context}

        Task:
        1. Evaluate trend (RSI, MACD, ATR, EMA structure)
        2. **CRITICAL**: Consider overall market trend. Be selective in downtrends.
        3. Sentiment score (-1.0 to 1.0)
        4. Confidence (0-100%). LOWER in unfavorable conditions.
        5. Reasoning (mention market trend if relevant)

        Output: VALID JSON ONLY
        {{
            "sentiment_score": float,
            "confidence": int,
            "reasoning": "string",
            "recommendation": {valid_actions}
        }}
        """

        try:
            if self._should_use_minimax_for_decision(tech_data=tech_data, intent=intent):
                try:
                    result = self._normalize_ai_result(
                        self._analyze_with_minimax_coding(prompt), intent=intent
                    )
                    model_name = f"MINIMAX_CODING:{self.minimax_model}"
                    result["model"] = model_name
                    self._mark_active_model(model_name)
                    return result
                except Exception as minimax_error:
                    # fallback to Gemini; keep loop alive
                    print(f"⚠️ [MiniMax Coding Error] {minimax_error} | fallback -> Gemini")

            result = self._normalize_ai_result(
                self._analyze_market_gemini(prompt), intent=intent
            )
            model_name = getattr(self.model, "model_name", "GEMINI")
            result["model"] = model_name
            self._mark_active_model(model_name)
            return result
        except Exception as e:
            safe_action = 'HOLD' if intent == 'EXIT' else 'WAIT'
            # Safe fallback decision to keep deterministic governor in control
            return {
                'sentiment_score': 0.0,
                'confidence': 0,
                'reasoning': f'AI analysis unavailable: {str(e)}',
                'recommendation': safe_action,
                'model': 'NONE'
            }

    @staticmethod
    def _extract_json_object(text: str):
        cleaned = str(text or "").replace('```json', '').replace('```', '').strip()
        if not cleaned:
            raise ValueError("Empty AI response")

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        start = cleaned.find("{")
        if start == -1:
            raise ValueError(f"No JSON object found in AI response: {cleaned[:180]}")

        depth = 0
        for idx in range(start, len(cleaned)):
            ch = cleaned[idx]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    snippet = cleaned[start:idx + 1]
                    return json.loads(snippet)

        raise ValueError("Unterminated JSON object in AI response")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
    def _analyze_market_gemini(self, prompt: str):
        """Retryable Gemini call + JSON parsing."""
        if not self.gemini_client:
            raise ExternalAPIError("Gemini client not configured")

        response = self.gemini_breaker.call_function(
            lambda: self.gemini_client.models.generate_content(
                model=self.gemini_model_name,
                contents=prompt,
                config={
                    "temperature": 0,
                    "max_output_tokens": 800,
                },
            )
        )
        return self._extract_json_object(getattr(response, "text", ""))

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
    def _analyze_with_minimax_coding(self, prompt: str):
        """Retryable MiniMax Coding Plan call + JSON parsing."""
        if not self.minimax_coding_key:
            raise ExternalAPIError("MINIMAX_CODING_PLAN_KEY not configured")

        url = f"{self.minimax_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.minimax_coding_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.minimax_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a quantitative crypto decision analyst. "
                        "Return only a valid JSON object with the requested schema."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": 800,
            "response_format": {"type": "json_object"},
        }

        def _request():
            response = requests.post(url, headers=headers, json=payload, timeout=self.minimax_timeout_sec)
            response_data = {}
            if "application/json" in (response.headers.get("content-type") or ""):
                try:
                    response_data = response.json()
                except Exception:
                    response_data = {}

            if response.status_code >= 400:
                err_msg = ""
                if isinstance(response_data, dict):
                    err_msg = (
                        response_data.get("base_resp", {}).get("status_msg")
                        or response_data.get("error", {}).get("message")
                        or ""
                    )
                if not err_msg:
                    err_msg = (response.text or "")[:200]
                raise ExternalAPIError(f"MiniMax HTTP {response.status_code}: {err_msg}")

            base_resp = response_data.get("base_resp", {}) if isinstance(response_data, dict) else {}
            status_code = base_resp.get("status_code", 0)
            if status_code not in (0, None):
                raise ExternalAPIError(
                    f"MiniMax API error {status_code}: {base_resp.get('status_msg', 'unknown error')}"
                )

            choices = response_data.get("choices", []) if isinstance(response_data, dict) else []
            if not choices:
                raise ExternalAPIError("MiniMax returned no choices")

            message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
            content = message.get("content", "") if isinstance(message, dict) else ""
            if not content:
                raise ExternalAPIError("MiniMax returned empty content")
            return content

        text = self.minimax_breaker.call_function(_request)
        return self._extract_json_object(text)
            
    # Note: The signal construction actually happens in THE JUDGE or whoever calls this.
    # Strategist just returns recommendation.
    # Let's check where the signal dict is built. 
    # It seems Judge builds it. We should check Judge.evaluate() or similar.
    # Wait, Strategist just returns JSON.
    # Let's check Judge.evaluate() in job_analysis.py (same file further down)

    def generate_performance_report(self, trade_history, days_range, is_sim=False, min_trades=20):
        """
        Backward-compatible text report entrypoint.
        Deterministic metrics are always computed first; AI layer is optional and gated.
        """
        review = self.analyze_performance_overview(
            days_range=days_range,
            is_sim=is_sim,
            min_trades=min_trades,
            include_ai=True,
            trade_history=trade_history,
        )
        ai_report = review.get("ai_report")
        if ai_report:
            return ai_report

        deterministic = review.get("deterministic", {})
        return (
            f"Deterministic performance snapshot ({review.get('period_days')}d) | "
            f"Trades: {deterministic.get('total_trades', 0)} | "
            f"Win rate: {deterministic.get('win_rate', 0):.1f}% | "
            f"Net PnL: ${deterministic.get('total_pnl', 0):,.2f}. "
            f"AI review skipped: {review.get('skip_reason', 'unknown')}."
        )

    def analyze_performance_overview(
        self,
        days_range=7,
        is_sim=False,
        min_trades=20,
        include_ai=True,
        trade_history=None,
    ):
        """
        Two-layer performance analysis:
        1) Deterministic metrics (source of truth)
        2) AI interpretation (only when sample size is sufficient)
        """
        try:
            period_days = max(1, int(days_range))
        except (TypeError, ValueError):
            period_days = 7
        try:
            minimum_trades = max(1, int(min_trades))
        except (TypeError, ValueError):
            minimum_trades = 20

        metrics = self._gather_performance_data(is_sim=is_sim, days_range=period_days)
        total_trades = int(metrics.get("total_trades", 0))
        sample_ready = total_trades >= minimum_trades

        result = {
            "mode": "PAPER" if is_sim else "LIVE",
            "period_days": period_days,
            "minimum_trades": minimum_trades,
            "sample_ready": sample_ready,
            "deterministic": metrics,
            "ai_model": None,
            "ai_report": None,
            "skip_reason": None,
        }

        if not include_ai:
            result["skip_reason"] = "include_ai_disabled"
            return result

        if not sample_ready:
            result["ai_model"] = "SKIPPED_LOW_SAMPLE"
            result["skip_reason"] = f"insufficient_trades:{total_trades}<{minimum_trades}"
            result["ai_report"] = (
                f"Skipped AI deep analysis because sample size is too small "
                f"({total_trades}/{minimum_trades} trades in {period_days}d). "
                f"Action: hold core parameters and collect more trades before optimization."
            )
            return result

        prompt = self._build_performance_prompt(
            performance_data=metrics,
            trade_history=trade_history,
            days_range=period_days,
            is_sim=is_sim,
            min_trades=minimum_trades,
        )

        if self.minimax_coding_key and self.prefer_minimax_for_decision:
            try:
                text = self._generate_report_text_with_minimax(prompt)
                result["ai_model"] = f"MINIMAX_CODING:{self.minimax_model}"
                result["ai_report"] = text
                return result
            except Exception as minimax_error:
                print(f"⚠️ [MiniMax Coding Error] performance report fallback -> Gemini ({minimax_error})")

        try:
            text = self._generate_report_text_with_gemini(prompt)
            result["ai_model"] = getattr(self.model, "model_name", "GEMINI")
            result["ai_report"] = text
        except Exception as gemini_error:
            result["ai_model"] = "NONE"
            result["skip_reason"] = f"ai_generation_failed:{gemini_error}"
            result["ai_report"] = (
                "AI performance report unavailable. Use deterministic metrics until provider recovers."
            )

        return result

    def _build_performance_prompt(self, performance_data, trade_history, days_range, is_sim, min_trades):
        recent_trades = trade_history[:20] if isinstance(trade_history, list) else []
        return f"""
        You are a Senior Portfolio Manager and Trading Analyst writing a comprehensive performance review.
        Period: Last {days_range} days.
        Mode: {"SIMULATION (Paper Trading)" if is_sim else "LIVE Trading"}
        Minimum sample threshold: {min_trades} closed trades.

        === DETERMINISTIC SOURCE-OF-TRUTH METRICS (DO NOT RE-CALCULATE) ===
        {json.dumps(performance_data, default=str, indent=2)}

        === RECENT CLOSED TRADES (OPTIONAL CONTEXT) ===
        {json.dumps(recent_trades, default=str, indent=2)}

        === ANALYSIS TASK ===
        1. Executive summary (2-3 sentences).
        2. Risk-adjusted performance assessment:
           - Expectancy, profit factor, win rate, drawdown behavior.
        3. Signal quality:
           - Approval/rejection pattern and key guardrails causing rejects.
        4. Regime/symbol behavior:
           - Best/worst symbols and whether behavior is stable or noisy.
        5. Action plan:
           - 3-5 prioritized actions with concrete thresholds.
        6. Overfitting control:
           - Explicitly state if data is still noisy and which parameters should NOT be changed yet.

        Output markdown with clear headers and concise bullets.
        Keep recommendations bounded by the deterministic metrics above.
        """

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
    def _generate_report_text_with_gemini(self, prompt: str):
        if not self.gemini_client:
            raise ExternalAPIError("Gemini client not configured")

        response = self.gemini_breaker.call_function(
            lambda: self.gemini_client.models.generate_content(
                model=self.gemini_model_name,
                contents=prompt,
                config={
                    "temperature": 0.2,
                    "max_output_tokens": 1400,
                },
            )
        )
        return str(getattr(response, "text", "")).strip()

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
    def _generate_report_text_with_minimax(self, prompt: str):
        if not self.minimax_coding_key:
            raise ExternalAPIError("MINIMAX_CODING_PLAN_KEY not configured")

        url = f"{self.minimax_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.minimax_coding_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.minimax_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a portfolio performance reviewer. "
                        "Use only the supplied deterministic metrics and avoid inventing numbers."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 1400,
        }

        def _request():
            response = requests.post(url, headers=headers, json=payload, timeout=self.minimax_timeout_sec)
            response_data = {}
            if "application/json" in (response.headers.get("content-type") or ""):
                try:
                    response_data = response.json()
                except Exception:
                    response_data = {}

            if response.status_code >= 400:
                err_msg = ""
                if isinstance(response_data, dict):
                    err_msg = (
                        response_data.get("base_resp", {}).get("status_msg")
                        or response_data.get("error", {}).get("message")
                        or ""
                    )
                if not err_msg:
                    err_msg = (response.text or "")[:200]
                raise ExternalAPIError(f"MiniMax HTTP {response.status_code}: {err_msg}")

            base_resp = response_data.get("base_resp", {}) if isinstance(response_data, dict) else {}
            status_code = base_resp.get("status_code", 0)
            if status_code not in (0, None):
                raise ExternalAPIError(
                    f"MiniMax API error {status_code}: {base_resp.get('status_msg', 'unknown error')}"
                )

            choices = response_data.get("choices", []) if isinstance(response_data, dict) else []
            if not choices:
                raise ExternalAPIError("MiniMax returned no choices for report generation")
            message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
            content = message.get("content", "") if isinstance(message, dict) else ""
            if not content:
                raise ExternalAPIError("MiniMax returned empty report content")
            return str(content).strip()

        return self.minimax_breaker.call_function(_request)

    def _get_exit_reason_stats(self, positions):
        """Calculate win rate and avg PnL by exit reason"""
        if not positions:
            return "No closed trades to analyze."
            
        from collections import defaultdict
        stats = defaultdict(lambda: {'count': 0, 'wins': 0, 'total_pnl': 0})
        
        for pos in positions:
            reason = pos.get('exit_reason', 'UNKNOWN')
            # Handle potential None value for exit_reason
            if not reason:
                 reason = 'UNKNOWN'
                 
            stats[reason]['count'] += 1
            pnl = float(pos.get('pnl', 0.0))
            if pnl > 0:
                stats[reason]['wins'] += 1
            stats[reason]['total_pnl'] += pnl
        
        # Format for AI
        output = []
        for reason, data in stats.items():
            count = data['count']
            if count > 0:
                win_rate = (data['wins'] / count * 100)
                avg_pnl = data['total_pnl'] / count
                output.append(f"- {reason}: {count} trades, {win_rate:.1f}% win rate, ${avg_pnl:.2f} avg PnL")
        
        return "\n".join(output) if output else "No data."

    def generate_performance_report_with_exit_stats(self, trade_history, days_range, is_sim=False):
        """Backward-compatible alias."""
        return self.generate_performance_report(trade_history, days_range, is_sim=is_sim)

    def _gather_performance_data(self, is_sim=False, days_range=7):
        """
        Gathers structured performance metrics from the database.
        """
        try:
            period_days = max(1, int(days_range))
        except (TypeError, ValueError):
            period_days = 7

        period_end = datetime.now(timezone.utc)
        period_start = period_end - timedelta(days=period_days)
        period_start_iso = period_start.isoformat()

        data = {
            'period_days': period_days,
            'period_start': period_start_iso,
            'period_end': period_end.isoformat(),
            'total_pnl': 0,
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'break_even': 0,
            'win_rate': 0,
            'best_trade': 0,
            'worst_trade': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'gross_profit': 0,
            'gross_loss': 0,
            'profit_factor': 0,
            'expectancy': 0,
            'payoff_ratio': 0,
            'max_drawdown_pct_period': 0,
            'total_signals': 0,
            'executed_signals': 0,
            'rejected_signals': 0,
            'approval_rate': 0,
            'rejection_reasons': {},
            'top_symbols': []
        }

        try:
            # Get closed positions with P&L
            closed_positions = self.db.table("positions")\
                .select("*, assets(symbol)")\
                .eq("is_sim", is_sim)\
                .eq("is_open", False)\
                .gte("closed_at", period_start_iso)\
                .execute()

            if closed_positions.data:
                pnl_values = [float(p['pnl']) for p in closed_positions.data if p.get('pnl') is not None]

                if pnl_values:
                    gross_profit = sum(p for p in pnl_values if p > 0)
                    gross_loss = abs(sum(p for p in pnl_values if p < 0))
                    data['total_pnl'] = sum(pnl_values)
                    data['total_trades'] = len(pnl_values)
                    data['wins'] = len([p for p in pnl_values if p > 0])
                    data['losses'] = len([p for p in pnl_values if p < 0])
                    data['break_even'] = len([p for p in pnl_values if p == 0])
                    data['win_rate'] = (data['wins'] / data['total_trades'] * 100) if data['total_trades'] > 0 else 0
                    data['best_trade'] = max(pnl_values) if pnl_values else 0
                    data['worst_trade'] = min(pnl_values) if pnl_values else 0

                    winning_trades = [p for p in pnl_values if p > 0]
                    losing_trades = [p for p in pnl_values if p < 0]
                    data['avg_win'] = sum(winning_trades) / len(winning_trades) if winning_trades else 0
                    data['avg_loss'] = sum(losing_trades) / len(losing_trades) if losing_trades else 0
                    data['gross_profit'] = gross_profit
                    data['gross_loss'] = gross_loss
                    data['profit_factor'] = (gross_profit / gross_loss) if gross_loss > 0 else (999.9 if gross_profit > 0 else 0)
                    data['expectancy'] = data['total_pnl'] / data['total_trades']
                    data['payoff_ratio'] = (
                        data['avg_win'] / abs(data['avg_loss'])
                        if data['avg_loss'] < 0 and data['avg_win'] > 0
                        else 0
                    )

                # Symbol performance
                symbol_pnl = {}
                for p in closed_positions.data:
                    symbol = p['assets']['symbol'] if p.get('assets') else 'UNKNOWN'
                    pnl = float(p['pnl']) if p.get('pnl') else 0
                    if symbol not in symbol_pnl:
                        symbol_pnl[symbol] = {'total_pnl': 0, 'trades': 0}
                    symbol_pnl[symbol]['total_pnl'] += pnl
                    symbol_pnl[symbol]['trades'] += 1

                # Sort by total P&L
                data['top_symbols'] = sorted(
                    [{'symbol': k, **v} for k, v in symbol_pnl.items()],
                    key=lambda x: x['total_pnl'],
                    reverse=True
                )[:10]

            # Drawdown profile in selected period (active session for requested mode)
            try:
                active_session = self.db.table("trading_sessions")\
                    .select("id")\
                    .eq("mode", "PAPER" if is_sim else "LIVE")\
                    .eq("is_active", True)\
                    .limit(1)\
                    .execute()
                if active_session.data:
                    session_id = active_session.data[0].get("id")
                    dd_rows = self.db.table("balance_snapshots")\
                        .select("drawdown_pct")\
                        .eq("session_id", session_id)\
                        .gte("snapshot_at", period_start_iso)\
                        .execute()
                    if dd_rows.data:
                        data['max_drawdown_pct_period'] = max(float(r.get("drawdown_pct") or 0) for r in dd_rows.data)
            except Exception:
                data['max_drawdown_pct_period'] = 0

            # Get trade signal statistics
            all_signals = self.db.table("trade_signals")\
                .select("status, judge_reason")\
                .eq("is_sim", is_sim)\
                .gte("created_at", period_start_iso)\
                .execute()

            if all_signals.data:
                data['total_signals'] = len(all_signals.data)
                data['executed_signals'] = len([s for s in all_signals.data if s['status'] == 'EXECUTED'])
                data['rejected_signals'] = len([s for s in all_signals.data if s['status'] == 'REJECTED'])
                data['approval_rate'] = (data['executed_signals'] / data['total_signals'] * 100) if data['total_signals'] > 0 else 0

                # Analyze rejection reasons
                rejection_reasons = {}
                for s in all_signals.data:
                    if s['status'] == 'REJECTED' and s.get('judge_reason'):
                        reason = s['judge_reason']
                        # Categorize reasons
                        if 'RSI' in reason:
                            key = 'RSI Veto'
                        elif 'EMA' in reason or 'Trend' in reason:
                            key = 'Trend Veto (EMA)'
                        elif 'MACD' in reason or 'Momentum' in reason:
                            key = 'Momentum Veto (MACD)'
                        elif 'confidence' in reason.lower() or 'Uncertainty' in reason:
                            key = 'AI Confidence Too Low'
                        elif 'Position Limit' in reason:
                            key = 'Max Positions Reached'
                        elif 'Duplicate' in reason:
                            key = 'Duplicate Position'
                        elif 'WAIT' in reason or 'HOLD' in reason:
                            key = 'AI Recommended WAIT/HOLD'
                        elif 'No open position' in reason:
                            key = 'SELL Without Position'
                        else:
                            key = 'Other'

                        rejection_reasons[key] = rejection_reasons.get(key, 0) + 1

                data['rejection_reasons'] = rejection_reasons

        except Exception as e:
            print(f"[Strategist] Error gathering performance data: {e}")

        return data

# --- THE JUDGE (LOGIC) ---
class TradeDecision(BaseModel):
    decision: str = Field(pattern="^(APPROVED|REJECTED)$")
    size: float
    reason: str

class Judge:
    """
    THE JUDGE (Rule-Based Validator)
    Combines AI opinion + Hard Risk Rules. Logic protects Capital.
    """
    def __init__(self):
        self.db = get_db()
        # Load config dynamically from DB
        self.config = self._load_config()

    def reload_config(self):
        """Refreshes configuration from the database."""
        try:
            if self.db:
                response = self.db.table("bot_config").select("*").execute()
                # Sanitize all values by removing literal quotes
                self.config = {item['key']: str(item['value']).replace('"', '').strip() for item in response.data}
                print(f"[Judge] Configuration reloaded.")
        except Exception as e:
            print(f"[Judge] Failed to reload config: {e}")

    def _load_config(self):
        try:
            # Mock data for blueprint if DB not connected
            if not self.db:
                return {'RSI_THRESHOLD': 75, 'AI_CONF_THRESHOLD': 60, 'MAX_RISK_PER_TRADE': 2.0}
            
            response = self.db.table("bot_config").select("*").execute()
            # Sanitize all values by removing literal quotes
            return {item['key']: str(item['value']).replace('"', '').strip() for item in response.data}
        except Exception as e:
            print(f"[Judge] Config load error: {e}")
            return {'RSI_THRESHOLD': 75, 'AI_CONF_THRESHOLD': 60}

    def evaluate(self, ai_data, tech_data, portfolio_balance, is_sim=False, asset_id=None):
        """
        Core Logic:
        0. Check Max Open Positions Limit (per mode).
        0b. Reject duplicate BUY for same asset.
        1. Check Hard Guardrails (RSI, Drawdown).
        2. Check AI Confidence.
        3. Calculate Position Size (Kelly or Fixed Risk).
        """

        # Reload config from DB to pick up dashboard changes
        self.reload_config()

        rsi = tech_data.get('rsi')
        ai_conf = ai_data.get('confidence')
        ai_rec = ai_data.get('recommendation')

        # --- 0. CHECK MAX POSITIONS LIMIT (per mode, BUY only) ---
        # SELL orders are always allowed so users can reduce holdings
        if ai_rec != 'SELL':
            max_positions = int(self.config.get('MAX_OPEN_POSITIONS', 5))

            try:
                # Count open positions for current mode only
                open_positions = self.db.table("positions")\
                    .select("id")\
                    .eq("is_open", True)\
                    .eq("is_sim", is_sim)\
                    .execute()

                current_count = len(open_positions.data) if open_positions.data else 0

                if current_count >= max_positions:
                    return TradeDecision(
                        decision="REJECTED",
                        size=0,
                        reason=f"Position Limit: {current_count}/{max_positions} positions open"
                    )
            except Exception as e:
                print(f"[Judge] Error checking positions: {e}")

        # --- 0b. DUPLICATE BUY CHECK (same asset) ---
        if ai_rec == 'BUY' and asset_id:
            try:
                existing = self.db.table("positions")\
                    .select("id")\
                    .eq("asset_id", asset_id)\
                    .eq("is_open", True)\
                    .eq("is_sim", is_sim)\
                    .execute()
                if existing.data and len(existing.data) > 0:
                    return TradeDecision(
                        decision="REJECTED",
                        size=0,
                        reason=f"Duplicate: Already holding open position for this asset"
                    )
            except Exception as e:
                print(f"[Judge] Error checking duplicate position: {e}")

        # --- 0c. SELL WITHOUT POSITION CHECK ---
        if ai_rec == 'SELL' and asset_id:
            try:
                has_position = self.db.table("positions")\
                    .select("id")\
                    .eq("asset_id", asset_id)\
                    .eq("is_open", True)\
                    .eq("is_sim", is_sim)\
                    .execute()
                if not has_position.data:
                    return TradeDecision(
                        decision="REJECTED",
                        size=0,
                        reason=f"No open position to sell"
                    )
            except Exception as e:
                print(f"[Judge] Error checking sell position: {e}")

        # --- 0d. DOWNTREND PROTECTION (BUY only) ---
        if ai_rec == 'BUY':
            downtrend_enabled = self.config.get('ENABLE_DOWNTREND_PROTECTION', 'false').lower() == 'true'

            if downtrend_enabled:
                market_trend = tech_data.get('market_trend', {})
                trend_type = market_trend.get('trend', 'NEUTRAL')
                trend_strength = market_trend.get('strength', 0)
                trend_confidence = market_trend.get('confidence', 0)
                protection_mode = self.config.get('DOWNTREND_PROTECTION_MODE', 'MODERATE')

                if protection_mode == 'STRICT':
                    if trend_type in ['DOWNTREND', 'STRONG_DOWNTREND']:
                        return TradeDecision(
                            decision="REJECTED",
                            size=0,
                            reason=f"Downtrend Protection (STRICT): Market in {trend_type} (confidence: {trend_confidence:.0f}%)"
                        )

                elif protection_mode == 'MODERATE':
                    if trend_type == 'STRONG_DOWNTREND':
                        return TradeDecision(
                            decision="REJECTED",
                            size=0,
                            reason=f"Downtrend Protection (MODERATE): Strong downtrend (strength: {trend_strength:.0f}%)"
                        )
                    elif trend_type == 'DOWNTREND':
                        downtrend_ai_boost = float(self.config.get('DOWNTREND_AI_BOOST', 20))
                        adjusted_min_conf = float(self.config.get('AI_CONF_THRESHOLD', 60)) + downtrend_ai_boost

                        if ai_conf < adjusted_min_conf:
                            return TradeDecision(
                                decision="REJECTED",
                                size=0,
                                reason=f"Downtrend Protection (MODERATE): AI confidence {ai_conf}% < {adjusted_min_conf:.0f}% (downtrend penalty)"
                            )

                elif protection_mode == 'SELECTIVE':
                    if trend_type in ['DOWNTREND', 'STRONG_DOWNTREND']:
                        price_vs_ema200 = market_trend.get('signals', {}).get('price_vs_ema200', 'BELOW')
                        price_position = market_trend.get('signals', {}).get('price_position', 0)

                        if price_vs_ema200 == 'BELOW' or price_position < 2:
                            return TradeDecision(
                                decision="REJECTED",
                                size=0,
                                reason=f"Downtrend Protection (SELECTIVE): Coin lacks relative strength"
                            )

        # --- 1. THE HARD GUARDRAILS ---

        # A. RSI Veto (Always Active)
        rsi_limit = float(self.config.get('RSI_THRESHOLD', 75))
        if ai_rec == 'BUY' and rsi > rsi_limit:
            return TradeDecision(decision="REJECTED", size=0, reason=f"Technical Veto: RSI {rsi:.1f} > {rsi_limit}")
            
        # B. Trend Check (Configurable)
        if self.config.get('ENABLE_EMA_TREND', 'false').lower() == 'true':
            ema_50 = tech_data.get('ema_50', 0)
            close = tech_data.get('close', 0)
            if ai_rec == 'BUY' and close < ema_50:
                return TradeDecision(decision="REJECTED", size=0, reason=f"Trend Veto: Price ${close:,.2f} < EMA50 ${ema_50:,.2f}")

        # C. Momentum Check (Configurable)
        if self.config.get('ENABLE_MACD_MOMENTUM', 'false').lower() == 'true':
            macd = tech_data.get('macd', 0)
            signal = tech_data.get('macd_signal', 0)
            if ai_rec == 'BUY' and macd < signal:
                return TradeDecision(decision="REJECTED", size=0, reason=f"Momentum Veto: MACD {macd:.4f} < Signal {signal:.4f}")

        # Rule: AI must be confident (BUY only; SELL should not be blocked by confidence)
        min_conf = float(self.config.get('AI_CONF_THRESHOLD', 60))
        if ai_rec != 'SELL' and ai_conf < min_conf:
            return TradeDecision(
                decision="REJECTED",
                size=0,
                reason=f"AI Uncertainty: {ai_conf}% < {min_conf}%"
            )

        # Rule: Explicitly REJECT 'WAIT' signals
        if ai_rec in ['WAIT', 'HOLD']:
             return TradeDecision(
                 decision="REJECTED", 
                 size=0, 
                 reason=f"AI Recommendation is {ai_rec}"
             )

        # --- 2. POSITION SIZING ---
        # SELL uses existing position quantity (handled by Sniper), skip sizing
        if ai_rec == 'SELL':
            return TradeDecision(
                decision="APPROVED",
                size=0,
                reason=f"SELL Approved (Conf: {ai_conf}%). Size determined by position."
            )

        # BUY: Calculate position size
        # Standardized Key: POSITION_SIZE_PCT
        # Default to 5% if not set
        pos_size_pct = float(self.config.get('POSITION_SIZE_PCT', 5.0)) / 100
        calculated_size = portfolio_balance * pos_size_pct

        # Apply downtrend size reduction
        downtrend_enabled = self.config.get('ENABLE_DOWNTREND_PROTECTION', 'false').lower() == 'true'
        if downtrend_enabled:
            market_trend = tech_data.get('market_trend', {})
            trend_type = market_trend.get('trend', 'NEUTRAL')

            if trend_type == 'DOWNTREND':
                reduction_pct = float(self.config.get('DOWNTREND_SIZE_REDUCTION_PCT', 30)) / 100
                calculated_size *= (1 - reduction_pct)
                print(f"[Judge] Downtrend: Reduced position size by {reduction_pct*100}%")
            elif trend_type == 'STRONG_DOWNTREND':
                calculated_size *= 0.5
                print(f"[Judge] Strong Downtrend: Reduced position size by 50%")

        # Apply MAX_RISK_PER_TRADE limit
        max_risk_pct = float(self.config.get('MAX_RISK_PER_TRADE', 10.0)) / 100
        max_risk_amount = portfolio_balance * max_risk_pct

        # Use the smaller of the two (more conservative)
        size = min(calculated_size, max_risk_amount)

        return TradeDecision(
            decision="APPROVED",
            size=size,
            reason=f"BUY Approved (Conf: {ai_conf}%) + Tech Clean. Sizing: {size:.2f}"
        )
