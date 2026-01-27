"""
Trade decision validation model (from Judge).

Moved from job_analysis.py for better organization.
"""

from pydantic import BaseModel, Field


class TradeDecision(BaseModel):
    """
    Judge's decision on whether to approve a trade.
    
    Example:
        decision = TradeDecision(
            decision="APPROVED",
            size=100.0,
            reason="All checks passed: RSI ok, balance ok, AI confidence high"
        )
    """
    
    decision: str = Field(pattern="^(APPROVED|REJECTED)$", description="Decision outcome")
    size: float = Field(ge=0, description="Order size in USDT")
    reason: str = Field(min_length=5, max_length=500, description="Decision rationale")
    
    class Config:
        json_schema_extra = {
            "example": {
                "decision": "APPROVED",
                "size": 100.0,
                "reason": "All checks passed: RSI ok, balance ok, AI confidence high"
            }
        }
