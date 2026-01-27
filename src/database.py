import os
from supabase import create_client, Client, ClientOptions
from dotenv import load_dotenv

# Error handling utilities
from src.utils import retry_db_operation, SimpleCache, DatabaseError, safe_execute

load_dotenv()

# Global config cache (5 minute TTL)
_config_cache = SimpleCache(default_ttl=300, max_size=100)

class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            url = os.environ.get("SUPABASE_URL")
            key = os.environ.get("SUPABASE_KEY")
            # In production, raise error if missing
            if not url or not key:
                 print("WARNING: Supabase credentials missing.")
                 return None
            
            # CRITICAL: Set timeout to prevent indefinite hangs
            opts = ClientOptions(postgrest_client_timeout=20)
            cls._instance = create_client(url, key, options=opts)
        return cls._instance

def get_db() -> Client:
    return Database()

@retry_db_operation(max_attempts=2)
def get_config(key: str, default=None):
    """
    Get config value from bot_config table with caching and retry.
    
    Args:
        key: Config key
        default: Default value if key not found
        
    Returns:
        Config value or default
    """
    # Try cache first
    cache_key = f"config:{key}"
    cached = _config_cache.get(cache_key)
    if cached is not None:
        return cached
    
    # Query database
    try:
        db = get_db()
        if not db:
            return default
            
        result = db.table('bot_config').select('value').eq('key', key).execute()
        
        if result.data and len(result.data) > 0:
            value = result.data[0]['value']
            # Remove quotes if present
            if isinstance(value, str):
                value = value.replace('"', '').strip()
            # Cache the result
            _config_cache.set(cache_key, value)
            return value
        else:
            return default
            
    except Exception as e:
        raise DatabaseError(
            f"Failed to get config '{key}'",
            context={'key': key, 'error': str(e)}
        )

def get_config_safe(key: str, default=None):
    """
    Safe wrapper for get_config that never raises, always returns default on error.
    
    Args:
        key: Config key
        default: Default value
        
    Returns:
        Config value or default (never raises)
    """
    return safe_execute(
        lambda: get_config(key, default),
        fallback=default,
        error_context={'key': key}
    )

