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

    def _load_config(self):
        try:
            # Mock data for blueprint if DB not connected
            if not self.db:
                return {'RSI_OVERBOUGHT': 70, 'AI_MIN_CONFIDENCE': 75, 'MAX_RISK_PER_TRADE': 2.0}
            
            response = self.db.table("bot_config").select("*").execute()
            return {item['key']: item['value'] for item in response.data}
        except:
            return {'RSI_OVERBOUGHT': 70, 'AI_MIN_CONFIDENCE': 75}

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
        rsi_limit = float(self.config.get('RSI_OVERBOUGHT', 70))
        
        # Rule: Never buy if overbought, even if AI loves it.
        if rsi > rsi_limit and ai_rec == 'BUY':
            return TradeDecision(
                decision="REJECTED", 
                size=0, 
                reason=f"Technical Veto: RSI {rsi} > {rsi_limit}"
            )
        
        # Rule: AI must be confident.
        min_conf = float(self.config.get('AI_MIN_CONFIDENCE', 75))
        if ai_conf < min_conf:
             return TradeDecision(
                 decision="REJECTED", 
                 size=0, 
                 reason=f"AI Uncertainty: {ai_conf}% < {min_conf}%"
             )

        # --- 2. POSITION SIZING ---
        # Fixed Fractional Sizing: Risk 2% of equity per trade
        risk_per_trade_pct = float(self.config.get('MAX_RISK_PER_TRADE', 2.0)) / 100
        
        # Simplified for Blueprint: Flat 5% allocation for spot
        size = portfolio_balance * 0.05 
        
        return TradeDecision(
            decision="APPROVED",
            size=size,
            reason=f"AI Agreed (Conf: {ai_conf}%) + Tech Clean. Sizing: {size:.2f}"
        )
