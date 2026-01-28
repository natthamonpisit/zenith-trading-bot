#!/bin/bash
echo "🚀 Starting Zenith OS..."

# 1. Start the Trading Bot (Worker) in Background
echo "🤖 Launching Trading Bot (main.py)..."
python main.py &

# 2. Start the Status Server (Web UI) in Foreground
echo "📊 Launching Status Server on Port $PORT..."
python status_server.py
