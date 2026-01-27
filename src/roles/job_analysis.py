import google.generativeai as genai
import os
import json
from tenacity import retry, stop_after_attempt, wait_fixed
from pydantic import BaseModel, Field
from src.database import get_db

# --- THE STRATEGIST (AI) ---
class Strategist:
    """
    THE STRATEGIST (AI Reasoning Engine)
    Uses Google Gemini to analyze technical indicators and news sentiment.
    """
    def __init__(self):
        # Ensure API Key is loaded
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        # Using Gemini 2.0 Flash for speed and reasoning balance
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        self.db = get_db()

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
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
            # Set explicit timeout (30s) to prevent infinite hanging
            response = self.model.generate_content(prompt, request_options={"timeout": 30})
            # Cleanup potential markdown formatting
            text = response.text.replace('```json', '').replace('```', '').strip()
            analysis = json.loads(text)
            return analysis
            
        except Exception as e:
            print(f"Strategist Error: {e}")
            return None

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

    def evaluate(self, ai_data, tech_data, portfolio_balance):
        """
        Core Logic:
        1. Check Hard Guardrails (RSI, Drawdown).
        2. Check AI Confidence.
        3. Calculate Position Size (Kelly or Fixed Risk).
        """
        
        rsi = tech_data.get('rsi')
        ai_conf = ai_data.get('confidence')
        ai_rec = ai_data.get('recommendation')
        
        # --- 1. THE HARD GUARDRAILS ---
        
        # A. RSI Veto (Always Active)
        rsi_limit = float(self.config.get('RSI_THRESHOLD', self.config.get('RSI_OVERBOUGHT', 75)))
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
        
        # Rule: AI must be confident.
        # Standardized Key: AI_CONFIDENCE_THRESHOLD
        min_conf = float(self.config.get('AI_CONF_THRESHOLD', self.config.get('AI_MIN_CONFIDENCE', 60)))
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
        size = portfolio_balance * pos_size_pct 
        
        return TradeDecision(
            decision="APPROVED",
            size=size,
            reason=f"AI Agreed (Conf: {ai_conf}%) + Tech Clean. Sizing: {size:.2f}"
        )
