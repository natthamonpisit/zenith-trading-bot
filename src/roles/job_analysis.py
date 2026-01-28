import google.generativeai as genai
import os
import json
from tenacity import retry, stop_after_attempt, wait_fixed
from pydantic import BaseModel, Field
from src.database import get_db

# Error handling utilities
from src.utils import CircuitBreaker, ExternalAPIError

# --- THE STRATEGIST (AI) ---
class Strategist:
    """
    THE STRATEGIST (AI Reasoning Engine)
    Uses Google Gemini to analyze technical indicators and news sentiment.
    """
    def __init__(self):
        # Initialize database first (needed for saving model info)
        self.db = get_db()
        
        # Ensure API Key is loaded
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if not gemini_key:
            print("⚠️ GEMINI_API_KEY not found in environment")
        
        genai.configure(api_key=gemini_key)
        
        # Dynamic model selection with fallback (after db init)
        self.model = self._select_best_model()
        
        # Circuit breaker for Gemini AI protection
        self.gemini_breaker = CircuitBreaker(
            name="GEMINI_AI",
            failure_threshold=3,  # Stricter for AI
            timeout=90.0  # Longer recovery for AI
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
        
        try:
            # List all available models
            available_models = genai.list_models()
            available_names = [m.name.split('/')[-1] for m in available_models 
                             if 'generateContent' in m.supported_generation_methods]
            
            print(f"🔍 Available Gemini models: {', '.join(available_names[:5])}...")
            
            # Try each preferred model in order
            for model_name in preferred_models:
                if model_name in available_names:
                    try:
                        model = genai.GenerativeModel(model_name)
                        selected_model_name = model_name
                        print(f"✅ Selected Gemini model: {model_name}")
                        
                        # Save to database for status monitoring
                        try:
                            self.db.table("bot_config").upsert({
                                "key": "AI_MODEL",
                                "value": model_name
                            }).execute()
                        except Exception as e:
                            print(f"⚠️ Failed to save AI model to DB: {e}")
                        
                        return model
                    except Exception as e:
                        print(f"⚠️ Failed to initialize {model_name}: {e}")
                        continue
            
            # If no preferred model works, use first available
            if available_names:
                fallback_model = available_names[0]
                selected_model_name = fallback_model
                print(f"⚠️ Using fallback model: {fallback_model}")
                
                # Save to database
                try:
                    self.db.table("bot_config").upsert({
                        "key": "AI_MODEL",
                        "value": fallback_model
                    }).execute()
                except:
                    pass
                
                return genai.GenerativeModel(fallback_model)
            
        except Exception as e:
            print(f"❌ Failed to list models: {e}")
        
        # Ultimate fallback (most stable)
        selected_model_name = 'gemini-1.5-flash'
        print(f"⚠️ Using hardcoded fallback: {selected_model_name}")
        
        # Save to database
        try:
            self.db.table("bot_config").upsert({
                "key": "AI_MODEL",
                "value": selected_model_name
            }).execute()
        except:
            pass
        
        return genai.GenerativeModel('gemini-1.5-flash')

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
    def analyze_market(self, snapshot_id, asset_symbol, tech_data):
        """
        Sends market data to Gemini and expects a strict JSON response.
        """
        
        prompt = f"""
        You are a Senior Crypto Trader & Risk Analyst (The Strategist). 
        Analyze the following asset: {asset_symbol}.
        
        Technical Data:
        Technical Data:
        {json.dumps(tech_data, default=str)}
        
        Task:
        1. Evaluate the trend based on RSI, MACD, and ATR.
        2. Assign a sentiment score (-1.0 to 1.0).
        3. Provide a confidence level (0-100%).
        4. Explain your reasoning concisely.
        
        Output format: VALID JSON ONLY.
        {{
            "sentiment_score": float,
            "confidence": int,
            "reasoning": "string",
            "recommendation": "BUY" | "SELL" | "WAIT"
        }}
        """
        
        
        try:
            # Call Gemini API with circuit breaker protection
            response = self.gemini_breaker.call_function(
                lambda: self.model.generate_content(prompt, request_options={"timeout": 30})
            )
            
            # Cleanup potential markdown formatting
            text = response.text.replace('```json', '').replace('```', '').strip()
            analysis = json.loads(text)
            return analysis
            
        except Exception as e:
            print(f"⚠️ [Gemini AI Error] analyze_market failed: {e}")
            # Fallback: Return WAIT recommendation (safe default)
            return {
                'sentiment_score': 0.0,
                'confidence': 0,
                'reasoning': f'AI analysis unavailable: {str(e)}',
                'recommendation': 'WAIT'
            }

    def generate_performance_report(self, trade_history, days_range, is_sim=False):
        """
        Generates a comprehensive performance report with structured data analysis.
        """
        # Gather structured performance data
        performance_data = self._gather_performance_data(is_sim)

        prompt = f"""
        You are a Senior Portfolio Manager and Trading Analyst writing a comprehensive performance review.
        Period: Last {days_range} days.
        Mode: {"SIMULATION (Paper Trading)" if is_sim else "LIVE Trading"}

        === STRUCTURED PERFORMANCE DATA ===

        **P&L Summary:**
        - Total Realized P&L: ${performance_data['total_pnl']:,.2f}
        - Total Trades Closed: {performance_data['total_trades']}
        - Winning Trades: {performance_data['wins']} ({performance_data['win_rate']:.1f}%)
        - Losing Trades: {performance_data['losses']}
        - Best Trade: ${performance_data['best_trade']:,.2f}
        - Worst Trade: ${performance_data['worst_trade']:,.2f}
        - Average Win: ${performance_data['avg_win']:,.2f}
        - Average Loss: ${performance_data['avg_loss']:,.2f}

        **Trade Signal Statistics:**
        - Total Signals Generated: {performance_data['total_signals']}
        - Approved (Executed): {performance_data['executed_signals']}
        - Rejected: {performance_data['rejected_signals']}
        - Approval Rate: {performance_data['approval_rate']:.1f}%

        **Judge Guardrail Breakdown (Rejection Reasons):**
        {json.dumps(performance_data['rejection_reasons'], indent=2)}

        **Top Traded Symbols:**
        {json.dumps(performance_data['top_symbols'], indent=2)}

        **Recent Trade History (Last 20):**
        {json.dumps(trade_history[:20] if trade_history else [], default=str, indent=2)}

        === ANALYSIS TASK ===

        1. **Executive Summary**: Provide a 2-3 sentence overview of overall performance.

        2. **P&L Analysis**:
           - Assess profitability and risk-adjusted returns
           - Comment on win rate and average win/loss ratio
           - Identify any concerning patterns

        3. **Signal Quality Review**:
           - Analyze the approval/rejection ratio
           - Which guardrails are triggering most? Is this appropriate?
           - Are there missed opportunities or over-filtering?

        4. **Symbol Performance**:
           - Which coins performed best/worst?
           - Any recommendations for whitelist/blacklist adjustments?

        5. **Strategy Recommendations**:
           - Specific parameter adjustments (RSI threshold, AI confidence, position sizing)
           - Risk management improvements
           - Timing or market condition observations

        6. **Action Items**:
           - 3-5 concrete, actionable recommendations ranked by priority

        Output: Well-formatted Markdown with headers, bullet points, and clear sections.
        Be data-driven and specific in your analysis. Avoid generic advice.
        """
        try:
            response = self.model.generate_content(prompt, request_options={"timeout": 90})
            return response.text
        except Exception as e:
            return f"Failed to generate report: {e}"

    def _gather_performance_data(self, is_sim=False):
        """
        Gathers structured performance metrics from the database.
        """
        data = {
            'total_pnl': 0,
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0,
            'best_trade': 0,
            'worst_trade': 0,
            'avg_win': 0,
            'avg_loss': 0,
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
                .execute()

            if closed_positions.data:
                pnl_values = [float(p['pnl']) for p in closed_positions.data if p.get('pnl') is not None]

                if pnl_values:
                    data['total_pnl'] = sum(pnl_values)
                    data['total_trades'] = len(pnl_values)
                    data['wins'] = len([p for p in pnl_values if p > 0])
                    data['losses'] = len([p for p in pnl_values if p <= 0])
                    data['win_rate'] = (data['wins'] / data['total_trades'] * 100) if data['total_trades'] > 0 else 0
                    data['best_trade'] = max(pnl_values) if pnl_values else 0
                    data['worst_trade'] = min(pnl_values) if pnl_values else 0

                    winning_trades = [p for p in pnl_values if p > 0]
                    losing_trades = [p for p in pnl_values if p < 0]
                    data['avg_win'] = sum(winning_trades) / len(winning_trades) if winning_trades else 0
                    data['avg_loss'] = sum(losing_trades) / len(losing_trades) if losing_trades else 0

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

            # Get trade signal statistics
            all_signals = self.db.table("trade_signals")\
                .select("status, judge_reason")\
                .eq("is_sim", is_sim)\
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

        # Rule: AI must be confident.
        min_conf = float(self.config.get('AI_CONF_THRESHOLD', 60))
        if ai_conf < min_conf:
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
