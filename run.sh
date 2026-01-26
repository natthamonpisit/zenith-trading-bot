echo "🔍 DEBUG: Environment Variables (PORT only):"
env | grep PORT
echo "🧪 Starting Diagnostic Flask Server on Port $PORT"
export FLASK_ENV=production
python diagnostic_server.py
