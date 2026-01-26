#!/bin/bash
set -e

# If PORT is not set, default to 8080
export PORT=${PORT:-8080}

echo "🚀 Starting Zenith Bot on PORT $PORT"

# Force Python output to be unbuffered
export PYTHONUNBUFFERED=1

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

# Run Bot in background
echo "🤖 Starting Trading Bot..."
python main.py &

# Run Streamlit in background to check health
streamlit run dashboard/app.py &
PID=$!

# Wait for 5 seconds and check if port is listening
sleep 5
echo "🔍 Checking internal connectivity..."
if curl -v http://0.0.0.0:$PORT > /dev/null; then
    echo "✅ Internal Health Check Passed!"
else
    echo "❌ Internal Health Check FAILED. Streamlit is not listening on $PORT"
    ps aux
    cat /proc/$PID/fd/1 || true # Try to read stdout
fi

# Bring process to foreground
wait $PID
