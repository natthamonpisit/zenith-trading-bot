import os
from supabase import create_client, Client, ClientOptions
from dotenv import load_dotenv

load_dotenv()

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
