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

    def generate_performance_report(self, trade_history, days_range):
        """
        Generates a summary report of trading performance.
        """
        prompt = f"""
        You are a Portfolio Manager writing a performance review.
        Period: Last {days_range} days.
        
        Trade History Data:
        {json.dumps(trade_history, default=str)}
        
        Task:
        1. Summarize the overall trading activity (Total signals, Win Rate if applicable, Strategy behavior).
        2. Identify patterns in the AI's decision making (Why were certain trades rejected?).
        3. Give constructive feedback on the strategy settings.
        4. Use a professional, encouraging tone.
        
        Output: Markdown formatted text.
        """
        try:
            response = self.model.generate_content(prompt, request_options={"timeout": 60})
            return response.text
        except Exception as e:
            return f"Failed to generate report: {e}"

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

    def evaluate(self, ai_data, tech_data, portfolio_balance, is_sim=False):
        """
        Core Logic:
        0. Check Max Open Positions Limit (per mode).
        1. Check Hard Guardrails (RSI, Drawdown).
        2. Check AI Confidence.
        3. Calculate Position Size (Kelly or Fixed Risk).
        """

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
            reason=f"AI Agreed (Conf: {ai_conf}%) + Tech Clean. Sizing: {size:.2f}"
        )
