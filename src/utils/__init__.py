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
)
from .retry import retry_with_backoff, retry_db_operation
from .cache import SimpleCache
from .circuit_breaker import CircuitBreaker

__all__ = [
    # Exceptions
    'TradingBotError',
    'DatabaseError',
    'ExternalAPIError',
    'CircuitBreakerOpenError',
    'ConfigurationError',
    # Utilities
    'retry_with_backoff',
    'retry_db_operation',
    'SimpleCache',
    'CircuitBreaker',
]
