"""
Trade signal validation model.

Validates all signal data before insertion into trade_signals table.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Literal


class TradeSignal(BaseModel):
    """
    Trade signal data model with validation.
    
    Example:
        signal = TradeSignal(
            asset_id=1,
            signal_type="BUY",
            entry_target=50000.0,
            entry_atr=250.5,
            status="PENDING",
            judge_reason="RSI oversold + MACD crossover",
            is_sim=True
        )
    """
    
    asset_id: int = Field(gt=0, description="Asset database ID")
    signal_type: Literal["BUY", "SELL", "WAIT"] = Field(description="Signal action")
    entry_target: float = Field(gt=0, description="Target entry price")
    entry_atr: float = Field(ge=0, default=0.0, description="ATR at signal creation")
    status: Literal["PENDING", "EXECUTED", "REJECTED"] = Field(description="Signal status")
    judge_reason: str = Field(min_length=1, max_length=500, description="Judge decision reason")
    is_sim: bool = Field(description="Is this a simulation signal")
    
    @field_validator('entry_target')
    @classmethod
    def validate_price(cls, v):
        """Validate price is reasonable"""
        if v <= 0:
            raise ValueError('Price must be positive')
        if v > 10_000_000:  # 10M cap for sanity
            raise ValueError('Price exceeds maximum allowed (10M)')
        return v
    
    @field_validator('entry_atr')
    @classmethod
    def validate_atr(cls, v):
        """Validate ATR is non-negative"""
        if v < 0:
            raise ValueError('ATR cannot be negative')
        return v
    
    @field_validator('judge_reason')
    @classmethod
    def validate_reason(cls, v):
        """Ensure reason is meaningful"""
        if len(v.strip()) < 5:
            raise ValueError('Judge reason must be at least 5 characters')
        return v.strip()
    
    class Config:
        json_schema_extra = {
            "example": {
                "asset_id": 1,
                "signal_type": "BUY",
                "entry_target": 50000.0,
                "entry_atr": 250.5,
                "status": "PENDING",
                "judge_reason": "RSI oversold + MACD crossover",
                "is_sim": True
            }
        }
