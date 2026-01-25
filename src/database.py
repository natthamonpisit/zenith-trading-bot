import os
from supabase import create_client, Client
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
            cls._instance = create_client(url, key)
        return cls._instance

def get_db() -> Client:
    return Database()
