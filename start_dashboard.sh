#!/bin/bash
# Railway Dashboard Startup Script
echo "🚀 Starting Zenith Dashboard..."
streamlit run dashboard/app.py --server.port=${PORT:-8501} --server.address=0.0.0.0
