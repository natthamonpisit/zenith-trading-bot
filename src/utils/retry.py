"""
Retry logic with exponential backoff for handling transient failures.

Uses tenacity library for robust retry mechanisms.
"""

import time
from functools import wraps
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log,
)
import logging

from .errors import DatabaseError, ExternalAPIError

logger = logging.getLogger(__name__)


def retry_with_backoff(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
    exceptions: tuple = (ExternalAPIError,),
):
    """
    Decorator for retrying a function with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        min_wait: Minimum wait time between retries in seconds (default: 1.0)
        max_wait: Maximum wait time between retries in seconds (default: 10.0)
        exceptions: Tuple of exception types to retry on (default: ExternalAPIError)
    
    Example:
        @retry_with_backoff(max_attempts=3, exceptions=(ExternalAPIError, TimeoutError))
        def fetch_data(symbol):
            return exchange.fetch_ticker(symbol)
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(exceptions),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO),
        reraise=True,
    )


def retry_db_operation(max_attempts: int = 2):
    """
    Specialized retry decorator for database operations.
    
    Shorter retry window since DB operations should be fast.
    
    Args:
        max_attempts: Maximum number of retry attempts (default: 2)
    
    Example:
        @retry_db_operation()
        def get_config(key):
            return db.table('bot_config').select('*').eq('key', key).execute()
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2.0),
        retry=retry_if_exception_type((DatabaseError, ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


def safe_execute(func, fallback=None, error_context: dict = None):
    """
    Execute a function safely with fallback value on error.
    
    Args:
        func: Function to execute
        fallback: Fallback value if function fails (default: None)
        error_context: Additional context for error logging
    
    Returns:
        Result of func() or fallback value on error
    
    Example:
        config = safe_execute(
            lambda: db.get_config('TRADING_MODE'),
            fallback='PAPER',
            error_context={'key': 'TRADING_MODE'}
        )
    """
    try:
        return func()
    except Exception as e:
        ctx = error_context or {}
        logger.warning(
            f"safe_execute failed, using fallback: {e} | Context: {ctx}",
            exc_info=True
        )
        return fallback
