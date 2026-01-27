"""
Custom exception classes for the trading bot.

All exceptions provide rich context for better debugging and error reporting.
"""


class TradingBotError(Exception):
    """
    Base exception for all trading bot errors.
    
    All custom exceptions inherit from this to allow catching bot-specific errors.
    """
    def __init__(self, message: str, context: dict = None):
        self.message = message
        self.context = context or {}
        super().__init__(self._format_message())
    
    def _format_message(self) -> str:
        """Format error message with context"""
        msg = self.message
        if self.context:
            ctx_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            msg = f"{msg} | Context: {ctx_str}"
        return msg


class DatabaseError(TradingBotError):
    """
    Database operation failed.
    
    Examples:
    - Connection timeout
    - Query execution error
    - Data not found
    """
    pass


class ExternalAPIError(TradingBotError):
    """
    External API call failed (CCXT, Gemini AI, etc.).
    
    Examples:
    - API timeout
    - Rate limit exceeded
    - Invalid response
    - Network error
    """
    pass


class CircuitBreakerOpenError(TradingBotError):
    """
    Circuit breaker is open, rejecting requests to protect the system.
    
    This is raised when too many consecutive failures have occurred,
    and the circuit breaker is preventing further requests to allow
    the downstream service to recover.
    """
    pass


class ConfigurationError(TradingBotError):
    """
    Configuration error or missing required config.
    
    Examples:
    - Missing environment variables
    - Invalid config values
    - Missing bot_config entries
    """
    pass


class ValidationError(TradingBotError):
    """
    Data validation failed.
    
    Examples:
    - Invalid signal data
    - Invalid position data
    - Schema mismatch
    """
    pass


class InsufficientBalanceError(TradingBotError):
    """
    Insufficient balance to execute trade.
    
    Specific error for balance checks to allow special handling.
    """
    pass
