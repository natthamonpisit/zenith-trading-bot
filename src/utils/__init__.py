"""
Utility modules for error handling, retry logic, caching, and circuit breakers.

This package provides robust error handling infrastructure for the trading bot.
"""

from .errors import (
    TradingBotError,
    DatabaseError,
    ExternalAPIError,
    CircuitBreakerOpenError,
    ConfigurationError,
    ValidationError,
    InsufficientBalanceError,
)
from .retry import retry_with_backoff, retry_db_operation
from .cache import SimpleCache
from .circuit_breaker import CircuitBreaker
from .rate_limiter import RateLimiter

def safe_execute(func, fallback=None, error_context=None):
    """Execute function and return fallback on any error"""
    try:
        return func()
    except Exception as e:
        print(f"⚠️ safe_execute error: {e} | context: {error_context}")
        return fallback

__all__ = [
    # Exceptions
    'TradingBotError',
    'DatabaseError',
    'ExternalAPIError',
    'CircuitBreakerOpenError',
    'ConfigurationError',
    'ValidationError',
    'InsufficientBalanceError',
    # Utilities
    'retry_with_backoff',
    'retry_db_operation',
    'SimpleCache',
    'CircuitBreaker',
    'RateLimiter',
    'safe_execute',
]
