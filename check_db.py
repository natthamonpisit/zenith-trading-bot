
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("Error: Missing SUPABASE_URL or SUPABASE_KEY")
    exit(1)

try:
    supabase: Client = create_client(url, key)
    # Try to insert a test log
    data = {"role": "System", "message": "Connection Test", "level": "INFO"}
    response = supabase.table("system_logs").insert(data).execute()
    print("SUCCESS: Connected to system_logs!")
except Exception as e:
    print(f"ERROR: {e}")
