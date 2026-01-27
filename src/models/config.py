"""
Bot configuration validation model.

Validates config key-value pairs before insertion into bot_config table.
"""

from pydantic import BaseModel, Field, field_validator


class BotConfig(BaseModel):
    """
    Bot configuration data model with validation.
    
    Example:
        config = BotConfig(
            key="TRADING_MODE",
            value="PAPER"
        )
    """
    
    key: str = Field(min_length=1, max_length=100, description="Config key name")
    value: str = Field(description="Config value (stored as string)")
    
    @field_validator('key')
    @classmethod
    def validate_key(cls, v):
        """
        Validate config key format.
        
        - Only alphanumeric and underscores
        - Uppercase only
        - No leading/trailing whitespace
        """
        v = v.strip()
        
        if not v:
            raise ValueError('Config key cannot be empty')
        
        # Only allow alphanumeric + underscores
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Config key must contain only alphanumeric characters, underscores, and hyphens')
        
        return v.upper()
    
    @field_validator('value')
    @classmethod
    def validate_value(cls, v):
        """Validate value is not empty and trim whitespace"""
        if v is None:
            raise ValueError('Config value cannot be None')
        
        v_str = str(v).strip()
        
        if not v_str:
            raise ValueError('Config value cannot be empty')
        
        return v_str
    
    class Config:
        json_schema_extra = {
            "example": {
                "key": "TRADING_MODE",
                "value": "PAPER"
            }
        }
