#!/bin/bash

# 1. Print Port for verification
echo "🚀 Railway Port Assigned: $PORT"

# 2. Generate Streamlit Config Explicitly
mkdir -p .streamlit
cat > .streamlit/config.toml <<EOF
[server]
headless = true
address = "0.0.0.0"
port = $PORT
enableCORS = false
enableXsrfProtection = false
fileWatcherType = "none"

[browser]
gatherUsageStats = false
EOF

echo "✅ Config generated with PORT=$PORT"
cat .streamlit/config.toml

# 3. Start Streamlit (Background)
# Wait a bit to ensure it binds
streamlit run dashboard/app.py &
STREAMLIT_PID=$!

sleep 5

# 4. Start Bot (Foreground)
# Use exec to ensure signals are passed, or just run python
# But we need both.
python -u main.py &
BOT_PID=$!

# 5. Monitor PIDs
wait $STREAMLIT_PID $BOT_PID
