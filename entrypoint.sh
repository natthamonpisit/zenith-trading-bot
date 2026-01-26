#!/bin/bash
set -e

# If PORT is not set, default to 8080
export PORT=${PORT:-8080}

echo "🚀 Starting Zenith Bot on PORT $PORT"

# Create .streamlit directory if not exists
mkdir -p .streamlit

# Force write config.toml to ensure correct bindings
echo "[server]
headless = true
address = '0.0.0.0'
port = $PORT
enableCORS = false
enableXsrfProtection = false
fileWatcherType = 'none'

[browser]
gatherUsageStats = false
" > .streamlit/config.toml

# Run Streamlit
# Note: launching in foreground to keep container alive
exec streamlit run dashboard/app.py
