#!/usr/bin/env python3
"""
Quick test for Minimax API key.
Usage:
  export MINIMAX_API_KEY=your_key_here
  python scripts/test_minimax.py

Or add MINIMAX_API_KEY to .env and run from project root.
"""
import os
import sys

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

# Load from .env if present (project root)
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.isfile(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                os.environ.setdefault(k, v)

API_KEY = os.environ.get("MINIMAX_API_KEY")
if not API_KEY or API_KEY in ("your_minimax_key_here", "your_key_here"):
    print("Missing MINIMAX_API_KEY. Set it in .env or: export MINIMAX_API_KEY=your_key")
    sys.exit(1)

url = "https://api.minimax.io/v1/text/chatcompletion_v2"
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}
payload = {
    "model": "M2-her",
    "messages": [
        {"role": "system", "name": "MiniMax AI", "content": "You are a helpful assistant."},
        {"role": "user", "name": "User", "content": "Say hello in one short sentence."},
    ],
}

def main():
    print("Calling Minimax API...")
    r = requests.post(url, json=payload, headers=headers, timeout=30)
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}

    if r.status_code == 200:
        base = data.get("base_resp", {})
        code = base.get("status_code", 0)
        if code == 0:
            msg = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            print("OK — Minimax API key works.")
            if msg:
                print("Reply:", msg[:200] + ("..." if len(msg) > 200 else ""))
            return
        print("API returned error:", base.get("status_msg", "Unknown"), f"(code={code})")
    else:
        err = data.get("base_resp", {}).get("status_msg") or data.get("error", {}).get("message") or r.text
        print("Request failed:", r.status_code, err)

    sys.exit(1)

if __name__ == "__main__":
    main()
