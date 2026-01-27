#!/bin/bash
echo "🚀 Starting Zenith OS..."

# 1. Start the Trading Bot (Worker) in Background
echo "🤖 Launching Trading Bot (main.py)..."
python main.py &

# 2. Start the Dashboard (UI) in Foreground
# Streamlit needs to bind to $PORT for Railway to detect health
echo "📊 Launching Dashboard on Port $PORT..."
streamlit run dashboard/app.py --server.port $PORT --server.address 0.0.0.0
