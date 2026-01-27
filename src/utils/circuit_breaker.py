"""
Circuit Breaker pattern implementation for protecting against cascading failures.

Prevents repeated calls to failing services, allowing them time to recover.
"""

import time
import threading
from enum import Enum
from typing import Callable, Any
import logging

from .errors import CircuitBreakerOpenError

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failure threshold reached, reject requests
    HALF_OPEN = "half_open" # Testing if service recovered


class CircuitBreaker:
    """
    Circuit Breaker implementation to prevent cascading failures.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, reject all requests
    - HALF_OPEN: After timeout, allow test requests to check recovery
    
    Example:
        breaker = CircuitBreaker(
            name="CCXT_API",
            failure_threshold=5,
            timeout=60
        )
        
        @breaker.call
        def fetch_price(symbol):
            return exchange.fetch_ticker(symbol)
        
        # Or manually
        try:
            result = breaker.call_function(lambda: exchange.fetch_ticker('BTC/USDT'))
        except CircuitBreakerOpenError:
            # Use fallback
            result = get_cached_price('BTC/USDT')
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        success_threshold: int = 2,
    ):
        """
        Initialize circuit breaker.
        
        Args:
            name: Name of the circuit (for logging)
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before moving to HALF_OPEN
            success_threshold: Successful calls in HALF_OPEN before closing
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.success_threshold = success_threshold
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._lock = threading.Lock()
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state"""
        return self._state
    
    def call_function(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function through circuit breaker.
        
        Args:
            func: Function to execute
          *args, **kwargs: Arguments for the function
            
        Returns:
            Result of func(*args, **kwargs)
            
        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: Whatever func() raises if circuit is closed/half-open
        """
        with self._lock:
            # Check if circuit should transition from OPEN to HALF_OPEN
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.timeout:
                    logger.info(f"[CircuitBreaker:{self.name}] Transitioning to HALF_OPEN")
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                else:
                    # Still in cooldown period
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is OPEN",
                        context={
                            'state': 'OPEN',
                            'failures': self._failure_count,
                            'timeout': self.timeout,
                        }
                    )
        
        # Execute function
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        """Handle successful call"""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                logger.info(
                    f"[CircuitBreaker:{self.name}] Success in HALF_OPEN "
                    f"({self._success_count}/{self.success_threshold})"
                )
                
                if self._success_count >= self.success_threshold:
                    logger.info(f"[CircuitBreaker:{self.name}] Closing circuit (service recovered)")
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on successful call
                self._failure_count = 0
    
    def _on_failure(self):
        """Handle failed call"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                # Failed while testing recovery, back to OPEN
                logger.warning(f"[CircuitBreaker:{self.name}] Failed in HALF_OPEN, reopening circuit")
                self._state = CircuitState.OPEN
                self._success_count = 0
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    logger.error(
                        f"[CircuitBreaker:{self.name}] Opening circuit "
                        f"(failures: {self._failure_count}/{self.failure_threshold})"
                    )
                    self._state = CircuitState.OPEN
    
    def call(self, func: Callable) -> Callable:
        """
        Decorator to wrap function with circuit breaker.
        
        Example:
            breaker = CircuitBreaker("MyAPI")
            
            @breaker.call
            def fetch_data():
                return api.get_data()
        """
        def wrapper(*args, **kwargs):
            return self.call_function(func, *args, **kwargs)
        return wrapper
    
    def get_stats(self) -> dict:
        """Get current circuit breaker statistics"""
        with self._lock:
            return {
                'name': self.name,
                'state': self._state.value,
                'failure_count': self._failure_count,
                'success_count': self._success_count,
                'threshold': self.failure_threshold,
                'timeout': self.timeout,
            }
    
    def reset(self):
        """Manually reset circuit breaker to CLOSED state"""
        with self._lock:
            logger.info(f"[CircuitBreaker:{self.name}] Manual reset to CLOSED")
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
