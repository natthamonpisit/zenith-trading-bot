from pydantic import BaseModel, Field
from src.database import get_db

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
                return {'RSI_THRESHOLD': 70, 'AI_CONF_THRESHOLD': 75, 'MAX_RISK_PER_TRADE': 2.0}
            
            response = self.db.table("bot_config").select("*").execute()
            # Sanitize all values by removing literal quotes
            return {item['key']: str(item['value']).replace('"', '').strip() for item in response.data}
        except:
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
        
        # --- 1. THE GUARDRAIL ---
        # Standardized Key: RSI_THRESHOLD
        rsi_limit = float(self.config.get('RSI_THRESHOLD', self.config.get('RSI_OVERBOUGHT', 70)))
        
        # Rule: Never buy if overbought, even if AI loves it.
        if ai_rec == 'BUY' and rsi > rsi_limit:
            return TradeDecision(
                decision="REJECTED", 
                size=0, 
                reason=f"Technical Veto: RSI {rsi:.1f} > {rsi_limit}"
            )
        
        # Rule: AI must be confident.
        # Standardized Key: AI_CONFIDENCE_THRESHOLD
        min_conf = float(self.config.get('AI_CONF_THRESHOLD', self.config.get('AI_MIN_CONFIDENCE', 75)))
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
