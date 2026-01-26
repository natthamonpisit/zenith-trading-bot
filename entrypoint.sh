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

# Run Streamlit in background FIRST (Priority)
echo "🌟 Starting Streamlit Dashboard..."
streamlit run dashboard/app.py &
PID=$!

# Wait loop for Port Binding (Max 30s)
echo "⏳ Waiting for Streamlit to bind port $PORT..."
for i in {1..30}; do
    if curl -s http://0.0.0.0:$PORT > /dev/null; then
        echo "✅ Streamlit is UP and LISTENING!"
        break
    fi
    sleep 1
    echo "."
done

# Start Bot in background (Delayed)
echo "🤖 Starting Trading Bot (Lazy Start)..."
python main.py &

# Keep container alive by waiting for Streamlit
wait $PID
