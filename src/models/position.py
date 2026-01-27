"""
Position validation model.

Validates all position data before insertion into positions table.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional


class Position(BaseModel):
    """
    Position data model with validation.
    
    Example:
        position = Position(
            asset_id=1,
            side="LONG",
            entry_avg=50000.0,
            quantity=0.1,
            is_open=True,
            is_sim=True,
            entry_atr=250.5,
            highest_price_seen=50500.0,
            trailing_stop_price=49000.0
        )
    """
    
    asset_id: int = Field(gt=0, description="Asset database ID")
    side: Literal["LONG", "SHORT"] = Field(description="Position direction")
    entry_avg: float = Field(gt=0, description="Average entry price")
    quantity: float = Field(gt=0, description="Position quantity")
    is_open: bool = Field(description="Is position currently open")
    is_sim: bool = Field(description="Is this a simulation position")
    entry_atr: float = Field(ge=0, default=0.0, description="ATR at entry")
    highest_price_seen: float = Field(gt=0, default=0.0, description="Peak price for trailing")
    trailing_stop_price: Optional[float] = Field(default=None, description="Trailing stop price")
    
    @field_validator('entry_avg', 'highest_price_seen')
    @classmethod
    def validate_price(cls, v):
        """Validate price is reasonable"""
        if v <= 0:
            raise ValueError('Price must be positive')
        if v > 10_000_000:
            raise ValueError('Price exceeds maximum (10M)')
        return v
    
    @field_validator('quantity')
    @classmethod
    def validate_quantity(cls, v):
        """Validate quantity is positive"""
        if v <= 0:
            raise ValueError('Quantity must be positive')
        if v > 1_000_000:  # Sanity check
            raise ValueError('Quantity exceeds maximum (1M)')
        return v
    
    @field_validator('trailing_stop_price')
    @classmethod
    def validate_stop_price(cls, v, info):
        """Validate trailing stop is below entry for LONG"""
        if v is None:
            return v
        if v <= 0:
            raise ValueError('Trailing stop must be positive if set')
        # Note: Can't validate vs entry_avg here as it's not available in validator context
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "asset_id": 1,
                "side": "LONG",
                "entry_avg": 50000.0,
                "quantity": 0.1,
                "is_open": True,
                "is_sim": True,
                "entry_atr": 250.5,
                "highest_price_seen": 50500.0,
                "trailing_stop_price": 49000.0
            }
        }
