from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def hello():
    port = os.environ.get('PORT', 'Unknown')
    return f"<h1>✅ Flask is ALIVE on Port {port}</h1><p>V2: Railway Start Command override cleared! Ready for action.</p>"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 Starting Flask on 0.0.0.0:{port}", flush=True)
    app.run(host='0.0.0.0', port=port)
