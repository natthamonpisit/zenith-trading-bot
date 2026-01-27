"""
Simple in-memory cache with TTL (Time To Live) for reducing redundant API/DB calls.

Thread-safe implementation for concurrent access.
"""

import time
import threading
from typing import Any, Optional
from collections import OrderedDict


class SimpleCache:
    """
    Thread-safe in-memory cache with TTL support.
    
    Features:
    - TTL-based expiration
    - LRU eviction when max_size is reached
    - Thread-safe operations
    - Cache hit/miss statistics
    
    Example:
        cache = SimpleCache(default_ttl=5.0, max_size=1000)
        
        # Store value
        cache.set('BTC/USDT:price', 50000.0, ttl=5)
        
        # Retrieve value
        price = cache.get('BTC/USDT:price')  # Returns 50000.0 or None if expired
        
        # Get stats
        stats = cache.get_stats()  # {'hits': 10, 'misses': 2, 'hit_rate': 0.83}
    """
    
    def __init__(self, default_ttl: float = 60.0, max_size: int = 1000):
        """
        Initialize cache.
        
        Args:
            default_ttl: Default time-to-live in seconds (default: 60)
            max_size: Maximum number of items before LRU eviction (default: 1000)
        """
        self.default_ttl = default_ttl
        self.max_size = max_size
        self._cache = OrderedDict()
        self._lock = threading.Lock()
        
        # Statistics
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Returns None if key doesn't exist or has expired.
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            value, expiry_time = self._cache[key]
            
            # Check if expired
            if time.time() > expiry_time:
                del self._cache[key]
                self._misses += 1
                return None
            
            # Move to end (LRU)
            self._cache.move_to_end(key)
            self._hits += 1
            return value
    
    def set(self, key: str, value: Any, ttl: Optional[float] = None):
        """
        Store value in cache with TTL.
        
        Args:
            key: Cache key
            value: Value to store
            ttl: Time-to-live in seconds (uses default_ttl if None)
        """
        ttl = ttl if ttl is not None else self.default_ttl
        expiry_time = time.time() + ttl
        
        with self._lock:
            # Add or update
            self._cache[key] = (value, expiry_time)
            self._cache.move_to_end(key)
            
            # Evict oldest if over limit
            if len(self._cache) > self.max_size:
                self._cache.popitem(last=False)  # Remove oldest
    
    def delete(self, key: str):
        """Remove key from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
    
    def clear(self):
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
    
    def get_stats(self) -> dict:
        """
        Get cache statistics.
        
        Returns:
            dict with 'hits', 'misses', 'hit_rate', 'size'
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            
            return {
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': round(hit_rate, 3),
                'size': len(self._cache),
                'max_size': self.max_size,
            }
    
    def cleanup_expired(self):
        """
        Manually remove all expired entries.
        
        Called automatically during get(), but can be called manually
        for housekeeping.
        """
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, (_, expiry) in self._cache.items()
                if current_time > expiry
            ]
            for key in expired_keys:
                del self._cache[key]
