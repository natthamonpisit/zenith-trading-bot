"""
Rate limiter using token bucket algorithm.

Protects against API rate limit violations.
"""

import time
from threading import Lock
from typing import Optional


class RateLimiter:
    """
    Token bucket rate limiter for API calls.
    
    Args:
        max_calls: Maximum number of calls allowed
        period: Time period in seconds
        
    Example:
        # Binance limit: 1200 requests per minute
        limiter = RateLimiter(max_calls=1200, period=60)
        
        if limiter.allow():
            api.call()
        else:
            print("Rate limit reached, waiting...")
    """
    
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = Lock()
        self._hits = 0
        self._blocks = 0
    
    def allow(self) -> bool:
        """
        Check if a call is allowed under the rate limit.
        
        Returns:
            True if call is allowed, False if rate limit exceeded
        """
        with self.lock:
            now = time.time()
            
            # Remove old calls outside the time window
            self.calls = [t for t in self.calls if now - t < self.period]
            
            if len(self.calls) < self.max_calls:
                self.calls.append(now)
                self._hits += 1
                return True
            else:
                self._blocks += 1
                return False
    
    def wait_if_needed(self, timeout: float = 10.0) -> bool:
        """
        Wait until rate limit allows the call (with timeout).
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if call is now allowed, False if timeout reached
        """
        start = time.time()
        
        while not self.allow():
            if time.time() - start > timeout:
                return False
            time.sleep(0.1)  # Small sleep to avoid busy-waiting
        
        return True
    
    def get_stats(self) -> dict:
        """
        Get rate limiter statistics.
        
        Returns:
            Dict with hits, blocks, and rate info
        """
        with self.lock:
            current_rate = len(self.calls)
            return {
                'hits': self._hits,
                'blocks': self._blocks,
                'current_calls_in_window': current_rate,
                'limit': self.max_calls,
                'period': self.period,
                'utilization': current_rate / self.max_calls if self.max_calls > 0 else 0
            }
    
    def reset_stats(self):
        """Reset statistics counters"""
        with self.lock:
            self._hits = 0
            self._blocks = 0
    
    def get_wait_time(self) -> Optional[float]:
        """
        Get estimated wait time until next call is allowed.
        
        Returns:
            Seconds to wait, or None if call is immediately allowed
        """
        with self.lock:
            if len(self.calls) < self.max_calls:
                return None  # Call allowed now
            
            # Need to wait for oldest call to expire
            oldest = min(self.calls)
            wait_until = oldest + self.period
            wait_time = max(0, wait_until - time.time())
            return wait_time
