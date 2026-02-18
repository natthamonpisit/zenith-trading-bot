"""
Entrypoint for dashboard API service.
"""

import os

import uvicorn


if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    reload_enabled = os.getenv("API_RELOAD", "false").strip().lower() == "true"

    uvicorn.run("src.api.server:app", host=host, port=port, reload=reload_enabled)
