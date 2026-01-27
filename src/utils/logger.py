"""
Structured logging utility for the trading bot.

Provides JSON-formatted logging with automatic timestamps, context fields,
and performance timing decorators.
"""

import logging
import json
import time
from datetime import datetime
from typing import Any, Dict, Optional, Callable
from functools import wraps


class StructuredLogger:
    """
    Structured JSON logger for better log parsing and monitoring.
    
    Features:
    - JSON format for easy parsing
    - Automatic timestamp
    - Context fields (role, symbol, etc.)
    - Performance timing
    
    Example:
        logger = StructuredLogger(__name__, role="Spy")
        logger.info("Fetching data", symbol="BTC/USDT", timeframe="1h")
        # Output: {"timestamp": "2026-01-27T16:30:00", "level": "INFO", "message": "Fetching data", "role": "Spy", "symbol": "BTC/USDT", "timeframe": "1h"}
    """
    
    def __init__(self, name: str, role: Optional[str] = None):
        """
        Initialize structured logger.
        
        Args:
            name: Logger name (usually __name__)
            role: Role name (e.g. "Spy", "Judge", "Sniper")
        """
        self.logger = logging.getLogger(name)
        self.role = role
        
        # Configure JSON formatter if not already configured
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(JSONFormatter())
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def info(self, message: str, **kwargs):
        """Log info message with context"""
        self._log(logging.INFO, message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error message with context"""
        self._log(logging.ERROR, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message with context"""
        self._log(logging.WARNING, message, **kwargs)
    
    def success(self, message: str, **kwargs):
        """Log success message (custom level)"""
        self._log(logging.INFO, message, level_name="SUCCESS", **kwargs)
    
    def _log(self, level: int, message: str, level_name: Optional[str] = None, **kwargs):
        """
        Internal log method with structured data.
        
        Args:
            level: Logging level
            message: Log message
            level_name: Override level name (e.g. "SUCCESS")
            **kwargs: Additional context fields
        """
        data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': level_name or logging.getLevelName(level),
            'message': message,
        }
        
        # Add role if set
        if self.role:
            data['role'] = self.role
        
        # Add all context fields
        data.update(kwargs)
        
        # Log as JSON string
        self.logger.log(level, json.dumps(data))


class JSONFormatter(logging.Formatter):
    """Format logs as JSON"""
    
    def format(self, record):
        """Format log record as JSON or pass through if already JSON"""
        try:
            # Try to parse as JSON (already formatted by StructuredLogger)
            msg = record.getMessage()
            json.loads(msg)  # Validate it's JSON
            return msg
        except (json.JSONDecodeError, ValueError):
            # Fallback: wrap plain message in JSON
            return json.dumps({
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'level': record.levelname,
                'message': record.getMessage(),
                'module': record.module
            })


def log_execution_time(logger: StructuredLogger, operation: Optional[str] = None):
    """
    Decorator to log function execution time.
    
    Args:
        logger: StructuredLogger instance
        operation: Optional operation name (defaults to function name)
    
    Usage:
        @log_execution_time(logger)
        def my_function(arg1, arg2):
            ...
        
        @log_execution_time(logger, operation="fetch_price")
        def fetch_ticker(symbol):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            op_name = operation or func.__name__
            start = time.time()
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start
                
                logger.info(
                    f"{op_name} completed",
                    operation=op_name,
                    duration_ms=round(duration * 1000, 2),
                    status="success"
                )
                return result
                
            except Exception as e:
                duration = time.time() - start
                
                logger.error(
                    f"{op_name} failed",
                    operation=op_name,
                    duration_ms=round(duration * 1000, 2),
                    status="error",
                    error=str(e),
                    error_type=type(e).__name__
                )
                raise
        
        return wrapper
    return decorator


# Global logger cache
_loggers: Dict[str, StructuredLogger] = {}


def get_logger(name: str, role: Optional[str] = None) -> StructuredLogger:
    """
    Get or create a structured logger.
    
    Args:
        name: Logger name (usually __name__)
        role: Role name (optional)
        
    Returns:
        StructuredLogger instance
    """
    key = f"{name}:{role}" if role else name
    
    if key not in _loggers:
        _loggers[key] = StructuredLogger(name, role)
    
    return _loggers[key]
